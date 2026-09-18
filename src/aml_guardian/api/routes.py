"""Rotas API-01, API-03 e API-09 (T1.11, `SPEC.md` §9.1): alerta, dossiê mascarado e saúde.

DT-05 e DT-11 nunca carregam dado pessoal em claro (só tokens, `contracts/ingestion.py` e `contracts/pipeline.py`):
devolvê-los tal como persistidos já satisfaz o mascaramento da API-03, sem transformação adicional.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from aml_guardian.api.auth import require_role
from aml_guardian.api.health import HealthResult, check_health
from aml_guardian.api.state import AppState
from aml_guardian.audit.chain import add_event
from aml_guardian.config.feriados import load_feriados
from aml_guardian.contracts.ingestion import Alert, AlertRecord, AlertState
from aml_guardian.contracts.runtime import Approval, ApprovalDecision, Budget, InvestigationState, Role
from aml_guardian.graph.build import build_graph, run_alert
from aml_guardian.graph.checkpoint import sqlite_checkpointer
from aml_guardian.persistence.repository import get_alert_record, save_alert_record
from aml_guardian.sanitizer.sanitizer import sanitize_alert

router = APIRouter()

_DECISION_TO_STATE = {
    ApprovalDecision.COMUNICAR: AlertState.APPROVED,
    ApprovalDecision.ARQUIVAR: AlertState.APPROVED,
    ApprovalDecision.DEVOLVER: AlertState.RETURNED,
}


class DecisionRequest(BaseModel):
    decision: ApprovalDecision
    justification: str


def _app_state(request: Request) -> AppState:
    return request.app.state.aml


def _record_from_state(alert: Alert, final_state: InvestigationState, now: datetime) -> AlertRecord:
    dossier = final_state.dossier
    return AlertRecord(
        alert_id=final_state.alert_id,
        state=final_state.state,
        triage_level=final_state.triage.level if final_state.triage else None,
        selected_at=alert.selected_at,
        prazo_interno=dossier.deadlines.prazo_interno if dossier else None,
        prazo_regulatorio_analise=dossier.deadlines.prazo_regulatorio_analise if dossier else None,
        failure_reason=final_state.failure_reason,
        created_at=now,
        updated_at=now,
    )


@router.post("/alerts", status_code=202)
def post_alert(
    alert: Alert,
    request: Request,
    _role: Role = Depends(require_role(Role.SISTEMA)),
) -> dict[str, str]:
    state = _app_state(request)
    now = datetime.now(UTC)

    if get_alert_record(alert.alert_id, db_path=state.db_path) is not None:
        raise HTTPException(status_code=409, detail={"code": "ALERT_ALREADY_EXISTS", "message": "alert_id já recebido"})

    sanitized = sanitize_alert(alert, vault=state.vault)
    if sanitized is AlertState.NEEDS_HUMAN:
        record = AlertRecord(
            alert_id=alert.alert_id,
            state=AlertState.NEEDS_HUMAN,
            selected_at=alert.selected_at,
            failure_reason="Sanitização falhou: dado inválido ou ambíguo (RF-02)",
            created_at=now,
            updated_at=now,
        )
        save_alert_record(record, db_path=state.db_path)
        return {"alert_id": str(alert.alert_id), "state": AlertState.NEEDS_HUMAN.value}

    initial_state = InvestigationState(
        alert_id=sanitized.alert_id,
        trace_id=uuid4(),
        state=AlertState.SANITIZED,
        sanitized_alert=sanitized,
        budget=Budget(tokens_used=0, started_at=now),
    )
    with sqlite_checkpointer(state.checkpoint_path) as checkpointer:
        final_state, _compiled, _config = run_alert(initial_state, state.graph_deps, checkpointer)

    save_alert_record(_record_from_state(alert, final_state, now), db_path=state.db_path)
    return {"alert_id": str(alert.alert_id), "state": final_state.state.value}


@router.get("/alerts/{alert_id}")
def get_alert(
    alert_id: UUID,
    request: Request,
    _role: Role = Depends(require_role(Role.ANALISTA, Role.COMPLIANCE_OFFICER)),
) -> AlertRecord:
    state = _app_state(request)
    record = get_alert_record(alert_id, db_path=state.db_path)
    if record is None:
        raise HTTPException(status_code=404, detail={"code": "ALERT_NOT_FOUND", "message": "alert_id desconhecido"})
    return record


@router.get("/dossiers/{alert_id}")
def get_dossier(
    alert_id: UUID,
    request: Request,
    _role: Role = Depends(require_role(Role.ANALISTA, Role.COMPLIANCE_OFFICER)),
) -> dict[str, object]:
    state = _app_state(request)
    with sqlite_checkpointer(state.checkpoint_path) as checkpointer:
        compiled = build_graph(state.graph_deps).compile(checkpointer=checkpointer)
        snapshot = compiled.get_state({"configurable": {"thread_id": str(alert_id)}})

    if not snapshot.values:
        raise HTTPException(status_code=404, detail={"code": "ALERT_NOT_FOUND", "message": "alert_id desconhecido"})

    final_state = InvestigationState.model_validate(snapshot.values)
    if final_state.dossier is None:
        raise HTTPException(
            status_code=404, detail={"code": "DOSSIER_NOT_FOUND", "message": "dossiê ainda não disponível"}
        )
    return final_state.dossier.model_dump(mode="json")


@router.get("/reidentify/{token}")
def get_reidentify(
    token: str,
    request: Request,
    _role: Role = Depends(require_role(Role.ANALISTA, Role.COMPLIANCE_OFFICER)),
) -> dict[str, str]:
    """API-04 — devolve o valor original de um token de PII; só existe em memória, nunca em log/persistência."""
    state = _app_state(request)
    value = state.vault.retrieve(token)
    if value is None:
        raise HTTPException(status_code=404, detail={"code": "TOKEN_NOT_FOUND", "message": "token desconhecido"})
    return {"token": token, "value": value}


def _proximo_dia_util(referencia: datetime) -> date:
    feriados = load_feriados()
    dia = referencia.date() + timedelta(days=1)
    try:
        while dia.weekday() >= 5 or feriados.is_feriado(dia):
            dia += timedelta(days=1)
    except ValueError as exc:
        # `config/feriados.yaml` cobre um período fechado por desenho (RF-09): fora dele, falha
        # explícita em vez de inventar dia útil (nunca aprovar comunicação com prazo incerto).
        raise HTTPException(status_code=500, detail={"code": "FERIADOS_FORA_DO_PERIODO", "message": str(exc)}) from exc
    return dia


@router.post("/alerts/{alert_id}/decision")
def post_decision(
    alert_id: UUID,
    body: DecisionRequest,
    request: Request,
    _role: Role = Depends(require_role(Role.COMPLIANCE_OFFICER)),
) -> AlertRecord:
    """API-02 — aceite do Compliance Officer (RF-12, DT-15); exige dossiê em `DRAFT_READY` no checkpoint."""
    state = _app_state(request)
    record = get_alert_record(alert_id, db_path=state.db_path)
    if record is None:
        raise HTTPException(status_code=404, detail={"code": "ALERT_NOT_FOUND", "message": "alert_id desconhecido"})
    if record.state in (AlertState.APPROVED, AlertState.RETURNED):
        # DT-15: decisão do compliance officer é ato único; repetir (ex.: retry de rede) não pode
        # duplicar `event_key` no hash-chain (UNIQUE, `persistence/db.py`) nem trocar o veredito já dado.
        raise HTTPException(
            status_code=409, detail={"code": "ALERT_ALREADY_DECIDED", "message": "alert_id já teve decisão registrada"}
        )

    with sqlite_checkpointer(state.checkpoint_path) as checkpointer:
        compiled = build_graph(state.graph_deps).compile(checkpointer=checkpointer)
        snapshot = compiled.get_state({"configurable": {"thread_id": str(alert_id)}})
    if not snapshot.values or InvestigationState.model_validate(snapshot.values).dossier is None:
        raise HTTPException(
            status_code=404, detail={"code": "DOSSIER_NOT_FOUND", "message": "dossiê ainda não disponível"}
        )

    now = datetime.now(UTC)
    prazo_comunicacao = _proximo_dia_util(now) if body.decision is ApprovalDecision.COMUNICAR else None
    approval = Approval(
        alert_id=alert_id,
        decision=body.decision,
        justification=body.justification,
        decided_by_role=Role.COMPLIANCE_OFFICER,
        decided_at=now,
        prazo_comunicacao=prazo_comunicacao,
    )

    novo_estado = _DECISION_TO_STATE[approval.decision]
    add_event(
        alert_id=str(alert_id),
        event_type="HUMAN_DECISION",
        event_key=f"{alert_id}:human_decision:1",
        actor=Role.COMPLIANCE_OFFICER,
        state_from=record.state,
        state_to=novo_estado,
        db_path=state.db_path,
    )
    record = record.model_copy(update={"state": novo_estado, "updated_at": now})
    save_alert_record(record, db_path=state.db_path)
    return record


@router.get("/health")
def get_health(request: Request) -> HealthResult:
    state = _app_state(request)
    result = check_health(state.health_deps)
    if result.status != "ok":
        raise HTTPException(status_code=503, detail=result.model_dump())
    return result
