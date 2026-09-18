"""Rotas API-01, API-03 e API-09 (T1.11, `SPEC.md` §9.1): alerta, dossiê mascarado e saúde.

DT-05 e DT-11 nunca carregam dado pessoal em claro (só tokens, `contracts/ingestion.py` e `contracts/pipeline.py`):
devolvê-los tal como persistidos já satisfaz o mascaramento da API-03, sem transformação adicional.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel

from aml_guardian.api.auth import require_role
from aml_guardian.api.health import HealthResult, check_health
from aml_guardian.api.state import AppState
from aml_guardian.audit.chain import AuditChain, add_event
from aml_guardian.config.feriados import load_feriados
from aml_guardian.contracts.ingestion import Alert, AlertRecord, AlertState
from aml_guardian.contracts.runtime import Approval, ApprovalDecision, Budget, InvestigationState, Role
from aml_guardian.graph.build import build_graph, run_alert
from aml_guardian.graph.checkpoint import sqlite_checkpointer
from aml_guardian.persistence.repository import (
    get_alert_record,
    get_ingestion_hash,
    list_alert_records,
    save_alert_record,
    save_ingestion_hash,
)
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


def _payload_sha256(alert: Alert) -> str:
    canonical = json.dumps(alert.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@router.post("/alerts", status_code=202)
def post_alert(
    alert: Alert,
    request: Request,
    response: Response,
    _role: Role = Depends(require_role(Role.SISTEMA)),
) -> dict[str, str]:
    state = _app_state(request)
    now = datetime.now(UTC)
    payload_sha256 = _payload_sha256(alert)

    previous_hash = get_ingestion_hash(alert.alert_id, db_path=state.db_path)
    if previous_hash is not None:
        if previous_hash != payload_sha256:
            raise HTTPException(status_code=409, detail={"code": "ALERT_ID_CONFLICT", "message": "payload divergente"})
        record = get_alert_record(alert.alert_id, db_path=state.db_path)
        if record is None:
            raise HTTPException(
                status_code=409, detail={"code": "ALERT_STATE_MISSING", "message": "estado inconsistente"}
            )
        response.status_code = 200
        return {"alert_id": str(alert.alert_id), "state": record.state.value}

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
        save_ingestion_hash(alert.alert_id, payload_sha256, db_path=state.db_path)
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
    save_ingestion_hash(alert.alert_id, payload_sha256, db_path=state.db_path)
    return {"alert_id": str(alert.alert_id), "state": final_state.state.value}


@router.get("/alerts")
def list_alerts_before_detail(
    request: Request,
    state_filter: AlertState | None = Query(default=None, alias="state"),
    em_risco: bool | None = None,
    _role: Role = Depends(require_role(Role.ANALISTA, Role.COMPLIANCE_OFFICER)),
) -> list[AlertRecord]:
    return list_alert_records(state_filter, em_risco, date.today(), _app_state(request).db_path)


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


@router.get("/alerts")
def list_alerts(
    request: Request,
    state_filter: AlertState | None = Query(default=None, alias="state"),
    em_risco: bool | None = None,
    _role: Role = Depends(require_role(Role.ANALISTA, Role.COMPLIANCE_OFFICER)),
) -> list[AlertRecord]:
    return list_alert_records(state_filter, em_risco, date.today(), _app_state(request).db_path)


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


@router.post("/dossiers/{alert_id}/reidentify")
def reidentify_dossier(
    alert_id: UUID,
    request: Request,
    response: Response,
    _role: Role = Depends(require_role(Role.ANALISTA, Role.COMPLIANCE_OFFICER)),
) -> dict[str, dict[str, str]]:
    state = _app_state(request)
    with sqlite_checkpointer(state.checkpoint_path) as checkpointer:
        snapshot = build_graph(state.graph_deps).compile(checkpointer=checkpointer).get_state(
            {"configurable": {"thread_id": str(alert_id)}}
        )
    if not snapshot.values:
        raise HTTPException(status_code=404, detail={"code": "ALERT_NOT_FOUND", "message": "alert_id desconhecido"})
    sanitized = InvestigationState.model_validate(snapshot.values).sanitized_alert
    tokens = {sanitized.sender_account, sanitized.sender_customer.name, sanitized.sender_customer.cpf_cnpj}
    tokens.update(account for tx in sanitized.transactions for account in (tx.sender_account, tx.receiver_account))
    values = {token: state.vault.retrieve(token) for token in tokens}
    if any(value is None for value in values.values()):
        raise HTTPException(status_code=410, detail={"code": "VAULT_UNAVAILABLE", "message": "Vault indisponível"})
    add_event(str(alert_id), "PII_REVEALED", f"{alert_id}:pii_revealed:1", _role, db_path=state.db_path)
    response.headers["Cache-Control"] = "no-store"
    return {"tokens": values}  # type: ignore[return-value]


@router.post("/dossiers/{alert_id}/submit")
def submit_dossier(alert_id: UUID, request: Request, _role: Role = Depends(require_role(Role.ANALISTA))) -> AlertRecord:
    state = _app_state(request)
    record = get_alert_record(alert_id, state.db_path)
    if record is None:
        raise HTTPException(status_code=404, detail={"code": "ALERT_NOT_FOUND", "message": "alert_id desconhecido"})
    if record.state is not AlertState.DRAFT_READY:
        raise HTTPException(
            status_code=409, detail={"code": "INVALID_STATE", "message": "dossiê não está em DRAFT_READY"}
        )
    now = datetime.now(UTC)
    updated = record.model_copy(update={"state": AlertState.SUBMITTED, "updated_at": now})
    add_event(
        str(alert_id),
        "DOSSIER_SUBMITTED",
        f"{alert_id}:dossier_submitted:1",
        Role.ANALISTA,
        record.state,
        AlertState.SUBMITTED,
        db_path=state.db_path,
    )
    save_alert_record(updated, state.db_path)
    return updated


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
@router.post("/dossiers/{alert_id}/approval")
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
    if record.state is not AlertState.SUBMITTED:
        # DT-15: decisão do compliance officer é ato único; repetir (ex.: retry de rede) não pode
        # duplicar `event_key` no hash-chain (UNIQUE, `persistence/db.py`) nem trocar o veredito já dado.
        raise HTTPException(
            status_code=409, detail={"code": "INVALID_STATE", "message": "aprovação exige SUBMITTED"}
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


@router.get("/audit/verify")
def verify_audit_before_detail(
    request: Request, _role: Role = Depends(require_role(Role.COMPLIANCE_OFFICER))
) -> dict[str, bool | int | None]:
    return AuditChain(_app_state(request).db_path).verify_details()


@router.get("/audit/{alert_id}")
def get_audit(
    alert_id: UUID, request: Request, _role: Role = Depends(require_role(Role.COMPLIANCE_OFFICER))
) -> list[dict[str, object]]:
    events = AuditChain(_app_state(request).db_path).get_events(str(alert_id))
    if not events:
        raise HTTPException(status_code=404, detail={"code": "AUDIT_NOT_FOUND", "message": "alert_id desconhecido"})
    return [event.model_dump(mode="json") for event in events]


@router.get("/audit/verify")
def verify_audit(
    request: Request, _role: Role = Depends(require_role(Role.COMPLIANCE_OFFICER))
) -> dict[str, bool | int | None]:
    return AuditChain(_app_state(request).db_path).verify_details()
