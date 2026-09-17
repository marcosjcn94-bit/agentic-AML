"""Cálculo dos indicadores agregados do DT-16 (T1.5, AGENTS.md §4.3, `features_version = 1`).

Nomes e formatos reproduzem `scripts/bench_ollama.py:128-146` (script não alterado, só sua forma é seguida).
Valores são inteiros, exceto F11 (1 casa decimal + `x`: cada dígito custa um token no tokenizador do Qwen).
F08 e F10 reaproveitam os detectores de `aml_guardian.triage.detectors` — a mesma lógica que produziu DT-06
(RF-03) — para nunca divergir da triagem. F06/F07/F14+ cobrem o alerta inteiro (sem a janela do detector de
camadas); F08 usa a janela de `camadas.janela_dias` (AGENTS.md §4.3, coluna "Cálculo").

MCP-01 (`window_days = 180`) e MCP-02 indisponíveis propagam `MCPIndisponivelError`: a decisão de levar o
alerta a `NEEDS_HUMAN` é do nó Investigação (T1.6), que engloba este pré-passo (AGENTS.md §2.3).
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import ROUND_HALF_UP, Decimal

from aml_guardian.config.triage import TriageRulesConfig, load_triage_rules
from aml_guardian.contracts.ingestion import PaymentType, SanitizedAlert, SanitizedTransaction
from aml_guardian.contracts.pipeline import Feature, InvestigationFeatures
from aml_guardian.mcp_servers.server import check_restriction_lists, get_customer_history
from aml_guardian.triage.detectors import (
    contrapartes,
    e_transfronteirica,
    par_especie_exterior,
    profundidade_camadas,
    transacoes_abaixo_limiar,
)
from aml_guardian.triage.engine import MCPIndisponivelError, RestrictionChecker

FEATURES_VERSION = 1
MCP01_WINDOW_DAYS = 180  # AGENTS.md §2.3, §4.3: pré-passo consulta MCP-01 com window_days = 180

HistoryFetcher = Callable[..., dict[str, object]]


def _arredonda(valor: Decimal) -> int:
    return int(valor.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _volume(transactions: list[SanitizedTransaction]) -> Decimal:
    return sum((t.amount_brl for t in transactions), Decimal("0"))


def _ids(transactions: list[SanitizedTransaction]) -> list[str]:
    return [t.transaction_id for t in transactions]


def _f01_tx_janela(alert: SanitizedAlert) -> Feature:
    return Feature(
        feature_id="F01", name="tx_janela", value=len(alert.transactions), transaction_ids=_ids(alert.transactions)
    )


def _f02_total_brl(alert: SanitizedAlert) -> Feature:
    total = _arredonda(_volume(alert.transactions))
    return Feature(feature_id="F02", name="total_brl", value=total, transaction_ids=_ids(alert.transactions))


def _f03_abaixo_limiar(alert: SanitizedAlert, rules: TriageRulesConfig) -> Feature:
    abaixo = transacoes_abaixo_limiar(alert, rules.detectores_criticos.fragmentacao)
    return Feature(feature_id="F03", name="abaixo_limiar", value=len(abaixo), transaction_ids=_ids(abaixo))


def _f04_dep_especie(alert: SanitizedAlert) -> Feature:
    txs = [t for t in alert.transactions if t.payment_type is PaymentType.ESPECIE_DEPOSITO]
    return Feature(feature_id="F04", name="dep_especie", value=len(txs), transaction_ids=_ids(txs))


def _f05_saida_pix_ted(alert: SanitizedAlert) -> Feature:
    txs = [
        t
        for t in alert.transactions
        if t.sender_account == alert.sender_account and t.payment_type in (PaymentType.PIX, PaymentType.TED)
    ]
    return Feature(feature_id="F05", name="saida_pix_ted", value=len(txs), transaction_ids=_ids(txs))


def _f06_contrap_entrada(entrada: dict[str, list[SanitizedTransaction]]) -> Feature:
    ids = [tid for txs in entrada.values() for tid in _ids(txs)]
    return Feature(feature_id="F06", name="contrap_entrada", value=len(entrada), transaction_ids=ids)


def _f07_contrap_saida(saida: dict[str, list[SanitizedTransaction]]) -> Feature:
    ids = [tid for txs in saida.values() for tid in _ids(txs)]
    return Feature(feature_id="F07", name="contrap_saida", value=len(saida), transaction_ids=ids)


def _f08_camadas(alert: SanitizedAlert, rules: TriageRulesConfig) -> Feature:
    cfg = rules.detectores_criticos.camadas
    profundidade, _distintas = profundidade_camadas(alert, cfg)
    entrada_janela, saida_janela = contrapartes(alert, cfg.janela_dias)
    ids = sorted({tid for txs in (*entrada_janela.values(), *saida_janela.values()) for tid in _ids(txs)})
    return Feature(feature_id="F08", name="camadas", value=profundidade, transaction_ids=ids)


def _f09_transfronteira(alert: SanitizedAlert) -> Feature:
    txs = [t for t in alert.transactions if e_transfronteirica(t)]
    return Feature(feature_id="F09", name="transfronteira", value=len(txs), transaction_ids=_ids(txs))


def _f10_especie_depois_exterior(alert: SanitizedAlert, rules: TriageRulesConfig) -> Feature:
    par = par_especie_exterior(alert, rules.detectores_criticos.especie_depois_exterior)
    valor = "sim" if par is not None else "nao"
    ids = [t.transaction_id for t in par] if par is not None else []
    return Feature(feature_id="F10", name="especie_depois_exterior", value=valor, transaction_ids=ids)


def _f11_vol_vs_media180d(alert: SanitizedAlert, historico: dict[str, object]) -> Feature:
    duracao_s = (alert.occurrence_window.end - alert.occurrence_window.start).total_seconds()
    duracao_dias = Decimal(str(max(duracao_s / 86_400, 1e-6)))
    total_180d = Decimal(str(historico["total_amount"]))
    # Média de volume para janelas de mesma duração nos 180 dias anteriores (AGENTS.md §4.3, F11). Sem histórico
    # suficiente para uma média positiva, usa um piso pequeno em vez de dividir por zero (decisão registrada
    # no relatório do T1.5: nenhum valor de referência é definido para esse caso pelo SPEC/AGENTS).
    media = max((total_180d / Decimal(180)) * duracao_dias, Decimal("0.01"))
    razao = _volume(alert.transactions) / media
    return Feature(
        feature_id="F11", name="vol_vs_media180d", value=f"{razao:.1f}x", transaction_ids=_ids(alert.transactions)
    )


def _f12_dias_ativos(alert: SanitizedAlert) -> Feature:
    dias = {t.timestamp.date() for t in alert.transactions}
    return Feature(feature_id="F12", name="dias_ativos", value=len(dias), transaction_ids=_ids(alert.transactions))


def _f13_listas(resultado_mcp02: dict[str, object]) -> Feature:
    valor = ",".join(f"{lista}:{resultado_mcp02[lista]}" for lista in ("pep", "ceis", "cnep"))
    return Feature(feature_id="F13", name="listas", value=valor, transaction_ids=[])


def _f14_mais_contrapartes(entrada: dict[str, list], saida: dict[str, list]) -> list[Feature]:
    tokens = sorted(set(entrada) | set(saida))
    linhas = []
    for token in tokens:
        txs_in = entrada.get(token, [])
        txs_out = saida.get(token, [])
        brl = _arredonda(_volume(txs_in) + _volume(txs_out))
        linhas.append((token, len(txs_in), len(txs_out), brl, _ids(txs_in) + _ids(txs_out)))
    # Ordenadas por brl decrescente (AGENTS.md §4.3); empate desfeito pelo token para resultado determinístico.
    linhas.sort(key=lambda linha: (-linha[3], linha[0]))
    return [
        Feature(feature_id=f"F{14 + i:02d}", name=token, value=f"in={n_in} out={n_out} brl={brl}", transaction_ids=ids)
        for i, (token, n_in, n_out, brl, ids) in enumerate(linhas)
    ]


def _consulta_mcp01(alert: SanitizedAlert, fetcher: HistoryFetcher) -> dict[str, object]:
    try:
        resultado = fetcher(customer_id=alert.sender_account, window_days=MCP01_WINDOW_DAYS)
    except Exception as exc:  # noqa: BLE001 - qualquer falha do MCP-01 é indisponibilidade (AGENTS.md §2.3)
        raise MCPIndisponivelError(f"MCP-01 indisponível no pré-passo: {exc}") from exc
    if not isinstance(resultado, dict) or resultado.get("status") != "success" or "total_amount" not in resultado:
        raise MCPIndisponivelError(f"MCP-01 respondeu fora do formato esperado: {resultado!r}")
    return resultado


def _consulta_mcp02(alert: SanitizedAlert, checker: RestrictionChecker) -> dict[str, object]:
    try:
        resultado = checker(customer_id=alert.sender_account, cpf_cnpj_token=alert.sender_customer.cpf_cnpj)
    except Exception as exc:  # noqa: BLE001 - qualquer falha do MCP-02 é indisponibilidade (AGENTS.md §2.3)
        raise MCPIndisponivelError(f"MCP-02 indisponível no pré-passo: {exc}") from exc
    if not isinstance(resultado, dict) or resultado.get("status") != "success":
        raise MCPIndisponivelError(f"MCP-02 respondeu fora do formato esperado: {resultado!r}")
    return resultado


def calcular_indicadores(
    alert: SanitizedAlert,
    rules: TriageRulesConfig | None = None,
    history_fetcher: HistoryFetcher = get_customer_history,
    restriction_checker: RestrictionChecker = check_restriction_lists,
) -> InvestigationFeatures:
    """Calcula F01-F13 e F14+ (`features_version = 1`) para o pré-passo da Investigação (DT-16, RF-05)."""
    cfg = rules or load_triage_rules()
    historico = _consulta_mcp01(alert, history_fetcher)
    resultado_mcp02 = _consulta_mcp02(alert, restriction_checker)
    entrada, saida = contrapartes(alert)

    features = [
        _f01_tx_janela(alert),
        _f02_total_brl(alert),
        _f03_abaixo_limiar(alert, cfg),
        _f04_dep_especie(alert),
        _f05_saida_pix_ted(alert),
        _f06_contrap_entrada(entrada),
        _f07_contrap_saida(saida),
        _f08_camadas(alert, cfg),
        _f09_transfronteira(alert),
        _f10_especie_depois_exterior(alert, cfg),
        _f11_vol_vs_media180d(alert, historico),
        _f12_dias_ativos(alert),
        _f13_listas(resultado_mcp02),
        *_f14_mais_contrapartes(entrada, saida),
    ]
    return InvestigationFeatures(alert_id=alert.alert_id, features=features, features_version=FEATURES_VERSION)
