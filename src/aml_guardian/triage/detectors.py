"""Detectores críticos do RF-03 (T1.4): fragmentação, camadas, espécie->exterior e lista de restrição.

Os quatro detectores são obrigatoriamente críticos (`config/triage_rules.yaml`): qualquer um disparado impede
`PROPOR_ARQUIVAMENTO` (RF-03, AGENTS.md §2.2). As funções de baixo nível (sem `FiredRule`) são reaproveitadas
pelo cálculo de indicadores do T1.5 (F06, F07, F08, F09, F10; AGENTS.md §4.3), para não duplicar a lógica.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from aml_guardian.config.triage import Camadas, EspecieDepoisExterior, Fragmentacao, ListaRestricaoDetector
from aml_guardian.contracts.ingestion import PaymentType, SanitizedAlert, SanitizedTransaction
from aml_guardian.contracts.pipeline import FiredRule

RULE_FRAGMENTACAO = "FRAGMENTACAO"
RULE_CAMADAS = "CAMADAS"
RULE_ESPECIE_EXTERIOR = "ESPECIE_DEPOIS_EXTERIOR"
RULE_LISTA_RESTRICAO = "LISTA_RESTRICAO"
RULE_SMURFING = "SMURFING"
RULE_LAYERED_FAN_IN = "LAYERED_FAN_IN"
RULE_LAYERED_FAN_OUT = "LAYERED_FAN_OUT"
RULE_STACKED_BIPARTITE = "STACKED_BIPARTITE"


def transacoes_abaixo_limiar(alert: SanitizedAlert, cfg: Fragmentacao) -> list[SanitizedTransaction]:
    """Transações com `amount_brl` abaixo do limiar, na ordem original (F03, AGENTS.md §4.3)."""
    return [t for t in alert.transactions if t.amount_brl < cfg.limiar_brl]


def detect_fragmentacao(alert: SanitizedAlert, cfg: Fragmentacao) -> FiredRule | None:
    """N transações abaixo do limiar concentradas numa janela de `cfg.janela_dias` (RF-03)."""
    abaixo = sorted(t.timestamp for t in transacoes_abaixo_limiar(alert, cfg))
    if len(abaixo) < cfg.min_transacoes:
        return None
    janela = timedelta(days=cfg.janela_dias)
    for inicio in range(len(abaixo) - cfg.min_transacoes + 1):
        fim = inicio + cfg.min_transacoes - 1
        if abaixo[fim] - abaixo[inicio] <= janela:
            return FiredRule(rule_id=RULE_FRAGMENTACAO, description=cfg.descricao, critical=True)
    return None


def contrapartes(
    alert: SanitizedAlert, janela_dias: int | None = None
) -> tuple[dict[str, list[SanitizedTransaction]], dict[str, list[SanitizedTransaction]]]:
    """Transações de entrada e saída do titular por contraparte.

    "Titular" é `alert.sender_account` (DT-04). Com `janela_dias`, restringe à janela mais recente do alerta
    (usado pelo detector de camadas); sem `janela_dias`, cobre todo o alerta (F06, F07 e F14+, AGENTS.md §4.3,
    já que o alerta chega recortado por `occurrence_window`, DT-01).
    """
    if not alert.transactions:
        return {}, {}
    titular = alert.sender_account
    referencia = max(t.timestamp for t in alert.transactions) if janela_dias is not None else None
    limite = timedelta(days=janela_dias) if janela_dias is not None else None
    entrada: dict[str, list[SanitizedTransaction]] = defaultdict(list)
    saida: dict[str, list[SanitizedTransaction]] = defaultdict(list)
    for t in alert.transactions:
        if limite is not None and referencia - t.timestamp > limite:
            continue
        if t.receiver_account == titular and t.sender_account != titular:
            entrada[t.sender_account].append(t)
        if t.sender_account == titular and t.receiver_account != titular:
            saida[t.receiver_account].append(t)
    return dict(entrada), dict(saida)


def profundidade_camadas(alert: SanitizedAlert, cfg: Camadas) -> tuple[int, set[str]]:
    """Profundidade fan-in/fan-out (0 a 2) e contrapartes distintas na janela do detector (F08, AGENTS.md §4.3)."""
    entrada, saida = contrapartes(alert, cfg.janela_dias)
    profundidade = (1 if entrada else 0) + (1 if saida else 0)
    distintas = set(entrada) | set(saida)
    return profundidade, distintas


def detect_camadas(alert: SanitizedAlert, cfg: Camadas) -> FiredRule | None:
    """Dispersão/concentração em camadas com profundidade >= `cfg.profundidade_minima` (RF-03)."""
    profundidade, distintas = profundidade_camadas(alert, cfg)
    if profundidade >= cfg.profundidade_minima and len(distintas) >= cfg.min_contrapartes:
        return FiredRule(rule_id=RULE_CAMADAS, description=cfg.descricao, critical=True)
    return None


def e_transfronteirica(t: SanitizedTransaction) -> bool:
    """`True` se a transação é uma transferência internacional ou cruza fronteira (F09, AGENTS.md §4.3)."""
    return t.payment_type is PaymentType.TRANSFERENCIA_INTERNACIONAL or t.sender_location != t.receiver_location


def par_especie_exterior(
    alert: SanitizedAlert, cfg: EspecieDepoisExterior
) -> tuple[SanitizedTransaction, SanitizedTransaction] | None:
    """Par (depósito em espécie, envio transfronteiriço) dentro de `cfg.janela_dias`; o par mais antigo achado."""
    janela = timedelta(days=cfg.janela_dias)
    depositos = sorted(
        (t for t in alert.transactions if t.payment_type is PaymentType.ESPECIE_DEPOSITO), key=lambda t: t.timestamp
    )
    envios = sorted((t for t in alert.transactions if e_transfronteirica(t)), key=lambda t: t.timestamp)
    for deposito in depositos:
        for envio in envios:
            if deposito.timestamp <= envio.timestamp <= deposito.timestamp + janela:
                return deposito, envio
    return None


def detect_especie_depois_exterior(alert: SanitizedAlert, cfg: EspecieDepoisExterior) -> FiredRule | None:
    """Depósito em espécie seguido de envio transfronteiriço dentro da janela (RF-03)."""
    if par_especie_exterior(alert, cfg) is not None:
        return FiredRule(rule_id=RULE_ESPECIE_EXTERIOR, description=cfg.descricao, critical=True)
    return None


def detect_lista_restricao(resultado_mcp02: dict[str, object], cfg: ListaRestricaoDetector) -> FiredRule | None:
    """`resultado_mcp02` é a saída sanitizada do MCP-02; dispara se qualquer lista de `cfg.listas` é `sim`."""
    if any(resultado_mcp02.get(lista) == "sim" for lista in cfg.listas):
        return FiredRule(rule_id=RULE_LISTA_RESTRICAO, description=cfg.descricao, critical=True)
    return None


def detect_smurfing(alert: SanitizedAlert, cfg: Fragmentacao) -> FiredRule | None:
    """Detecta fragmentação distribuída entre várias contrapartes, sem usar rótulo do alerta."""
    abaixo = transacoes_abaixo_limiar(alert, cfg)
    contrapartes_entrada = {t.sender_account for t in abaixo if t.receiver_account == alert.sender_account}
    if len(abaixo) >= cfg.min_transacoes and len(contrapartes_entrada) >= 2:
        return FiredRule(
            rule_id=RULE_SMURFING, description="Fragmentação distribuída entre contrapartes", critical=True
        )
    return None


def detect_network_shapes(alert: SanitizedAlert, cfg: Camadas) -> list[FiredRule]:
    """Classifica fan-in/fan-out/bipartite por estrutura, de forma determinística."""
    entrada, saida = contrapartes(alert, cfg.janela_dias)
    rules: list[FiredRule] = []
    if len(entrada) >= cfg.min_contrapartes:
        rules.append(
            FiredRule(rule_id=RULE_LAYERED_FAN_IN, description="Múltiplas entradas para o titular", critical=True)
        )
    if len(saida) >= cfg.min_contrapartes:
        rules.append(
            FiredRule(rule_id=RULE_LAYERED_FAN_OUT, description="Múltiplas saídas do titular", critical=True)
        )
    if len(entrada) >= 2 and len(saida) >= 2:
        rules.append(
            FiredRule(rule_id=RULE_STACKED_BIPARTITE, description="Entradas e saídas distribuídas", critical=True)
        )
    return rules
