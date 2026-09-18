"""Gates Go/No-Go do `SPEC.md` §10 (T1.13): gate não medido por este script aparece como "não medida", nunca
"aprovado" — o `Pronto quando` da tarefa proíbe declarar aprovação sem evidência (`TASKS.md` T1.13).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from aml_guardian.config.baseline import BaselineConfig

NAO_MEDIDA = "não medida"
MEDIDA = "medida"


@dataclass(frozen=True)
class GateResultado:
    metrica: str
    formula: str
    gate: str
    status: str  # "medida" | "não medida"
    valor: str | None
    aprovado: bool | None
    nota: str | None = None


def percentil(valores: list[float], p: float) -> float:
    """Percentil `p` (0-100) por interpolação linear sobre `valores` ordenados; `valores` não pode ser vazio."""
    if not valores:
        raise ValueError("percentil requer ao menos um valor")
    ordenados = sorted(valores)
    if len(ordenados) == 1:
        return ordenados[0]
    posicao = (p / 100) * (len(ordenados) - 1)
    piso = math.floor(posicao)
    teto = math.ceil(posicao)
    if piso == teto:
        return ordenados[int(posicao)]
    fracao = posicao - piso
    return ordenados[piso] + (ordenados[teto] - ordenados[piso]) * fracao


def _nao_medida(metrica: str, formula: str, gate: str, nota: str) -> GateResultado:
    return GateResultado(
        metrica=metrica,
        formula=formula,
        gate=gate,
        status=NAO_MEDIDA,
        valor=None,
        aprovado=None,
        nota=nota,
    )


def _gate_recall() -> GateResultado:
    return _nao_medida(
        "Recall crítico",
        "RNF-01",
        "= 100%",
        "Exige rodar o golden set completo (data/golden/v1, 500 alertas) pelo pipeline real e comparar com o "
        "rótulo verdadeiro do SAML-D; reservado para o marco que fecha RF-03/RNF-01 (TASKS.md §5, M3).",
    )


def _gate_grounding() -> GateResultado:
    return _nao_medida(
        "Grounding",
        "RNF-02",
        "bruto ≥ 99% e final 0",
        "O Revisor (T1.8) já impõe grounding final 0 por construção (citação não verificada nunca chega ao "
        "dossiê) e `pytest -k review` cobre a rejeição; a taxa bruta agregada sobre o golden set fica para M4.",
    )


def _gate_fp() -> GateResultado:
    return _nao_medida(
        "Redução de falsos positivos",
        "1 − FP_pipeline / FP_baseline",
        "≥ 65%",
        "Exige rodar o golden set completo pelo pipeline real e contar dossiês COS/NEEDS_HUMAN sobre os alertas "
        "normais; reservado para M7 (avaliação Go/No-Go).",
    )


def _gate_tokens() -> GateResultado:
    return _nao_medida(
        "Redução de tokens",
        "SPEC.md §3.3",
        "> 70%",
        "Falta o baseline de tokens do processo manual/legado para comparação; os tokens do fluxo agentic "
        "(tokens_in/tokens_out do evento MODEL_CALLED) já são medidos por alerta, mas sem referência ainda.",
    )


def _gate_prazo() -> GateResultado:
    return _nao_medida(
        "Prazo interno",
        "SPEC.md §3.1",
        "100% dentro",
        "É uma métrica de operação ao longo do tempo (prazo_interno vs. data real de conclusão); não se aplica "
        "a uma amostra sintética executada em lote único.",
    )


def _gate_privacidade() -> GateResultado:
    return _nao_medida(
        "Privacidade",
        "RNF-05",
        "0 ocorrências",
        "Coberto separadamente por `pytest -k canary` (T1.12) sobre prompts, logs e `data/app.sqlite`; este "
        "script não repete a varredura para não duplicar evidência.",
    )


def gate_velocidade(latencia_media_min: float, baseline: BaselineConfig) -> GateResultado:
    velocidade = baseline.tempo_manual_min / (latencia_media_min + baseline.tempo_revisao_min)
    return GateResultado(
        metrica="Velocidade",
        formula="tempo_manual_min / (latência_média_min + baseline.tempo_revisao_min)",
        gate="≥ 3x",
        status=MEDIDA,
        valor=f"{velocidade:.2f}x",
        aprovado=velocidade >= 3,
        nota=f"tempo_manual_min={baseline.tempo_manual_min}, tempo_revisao_min={baseline.tempo_revisao_min} "
        f"(config/baseline.yaml, provisórios); latência_média_min da amostra sintética, não do golden set.",
    )


def gate_latencia(p95_ms: float) -> GateResultado:
    p95_s = p95_ms / 1000
    return GateResultado(
        metrica="Latência",
        formula="RNF-03",
        gate="p95 < 20 s",
        status=MEDIDA,
        valor=f"{p95_s:.2f} s",
        aprovado=p95_s < 20,
        nota="p95 do fluxo INVESTIGAR completo (grafo) sobre amostra sintética, não o golden set inteiro.",
    )


def gate_auditoria(valido: bool) -> GateResultado:
    return GateResultado(
        metrica="Integridade da auditoria",
        formula="API-08 após a execução",
        gate="valid = true",
        status=MEDIDA,
        valor=str(valido),
        aprovado=valido,
        nota="Cadeia recalculada sobre o banco de auditoria da amostra desta execução.",
    )


def avalia_gates(latencias_ms: list[float], baseline: BaselineConfig, auditoria_valida: bool) -> list[GateResultado]:
    """Todos os 9 gates do `SPEC.md` §10; só Latência, Velocidade e Integridade da auditoria são medidos no M1.

    `latencias_ms` vazio levanta `ValueError` (nenhum alerta rodou, nada a medir) em vez de `ZeroDivisionError`.
    """
    if not latencias_ms:
        raise ValueError("avalia_gates requer ao menos uma amostra de latência")
    media_ms = sum(latencias_ms) / len(latencias_ms)
    p95_ms = percentil(latencias_ms, 95)
    latencia_media_min = (media_ms / 1000) / 60
    return [
        _gate_recall(),
        _gate_grounding(),
        _gate_fp(),
        gate_velocidade(latencia_media_min, baseline),
        _gate_tokens(),
        gate_latencia(p95_ms),
        _gate_prazo(),
        _gate_privacidade(),
        gate_auditoria(auditoria_valida),
    ]
