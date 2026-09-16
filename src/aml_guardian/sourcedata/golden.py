"""Conjunto de desenvolvimento e golden set `v1` (T0.9, `SPEC.md` §8.3, ADR-014).

Particiona `core_sintetico` por conta remetente em pool de desenvolvimento e pool golden, classifica cada
alerta gerado pelo monitoramento legado (T0.8) pela tipologia real do SAML-D das suas transações, e seleciona
uma amostra determinística estratificada (seed) que é congelada em manifesto com hash (`golden_manifest.py`).

Golden set MUST NOT ser usado para calibrar regras de triagem — ajuste usa `alertas_desenvolvimento()`.
"""

from __future__ import annotations

import random
import sqlite3
from collections import Counter, defaultdict
from collections.abc import Mapping
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from aml_guardian.config.alert_rules import AlertRulesConfig
from aml_guardian.contracts.ingestion import Alert
from aml_guardian.sourcedata.alert_generator import gera_alertas
from aml_guardian.sourcedata.core_db import conecta
from aml_guardian.sourcedata.mapping import SamlDMapping


class GoldenSetError(ValueError):
    """Estrato sem candidatos suficientes para a quota, ou quota total acima da disponibilidade (ADR-014)."""


def _distribui_agua(disponibilidade: Mapping[str, int], total: int) -> dict[str, int]:
    """Distribui `total` entre as chaves de `disponibilidade` por partilha máx-mín (água), nunca excedendo a
    disponibilidade de cada uma. Rótulos escassos são travados na própria disponibilidade e o resto é
    redistribuído igualmente entre os demais; a sobra indivisível vai para os primeiros em ordem alfabética,
    para o resultado ser determinístico e não depender de ordem de iteração de dict/set (SPEC.md §8.3)."""
    if sum(disponibilidade.values()) < total:
        raise GoldenSetError(f"disponibilidade total {sum(disponibilidade.values())} menor que a quota pedida {total}")
    travados: dict[str, int] = {}
    livres = set(disponibilidade)
    restante = total
    while livres:
        cota_base = restante // len(livres)
        escassos = {rotulo for rotulo in livres if disponibilidade[rotulo] <= cota_base}
        if not escassos:
            break
        for rotulo in escassos:
            travados[rotulo] = disponibilidade[rotulo]
            restante -= disponibilidade[rotulo]
        livres -= escassos
    if livres:
        cota_base, sobra = divmod(restante, len(livres))
        for indice, rotulo in enumerate(sorted(livres)):
            travados[rotulo] = cota_base + (1 if indice < sobra else 0)
    return travados


def estrato_de_alerta(alerta: Alert, rotulos: Mapping[str, str], mapping: SamlDMapping) -> str | None:
    """Estrato = a única tipologia suspeita presente nas transações do alerta (rótulo bruto do SAML-D), ou,
    se nenhuma transação for suspeita, o rótulo normal DOMINANTE (maior contagem; empate por ordem alfabética).
    Devolve `None` quando o alerta mistura 2+ tipologias suspeitas distintas — confirmado ausente nos dados
    reais (T0.9 Ask First), mas tratado explicitamente para não presumir invariante não garantida por schema."""
    rotulos_do_alerta = [rotulos[t.transaction_id] for t in alerta.transactions]
    suspeitos = sorted({rotulo for rotulo in rotulos_do_alerta if mapping.is_suspeito(rotulo)})
    if len(suspeitos) > 1:
        return None
    if len(suspeitos) == 1:
        return suspeitos[0]
    contagem = Counter(rotulo for rotulo in rotulos_do_alerta if rotulo in mapping.normais)
    if not contagem:
        raise GoldenSetError(f"alerta {alerta.alert_id}: nenhuma transação com rótulo conhecido do mapeamento")
    maior = max(contagem.values())
    return min(rotulo for rotulo, quantidade in contagem.items() if quantidade == maior)


@dataclass(frozen=True)
class ParticaoContas:
    """Contas remetentes particionadas para o golden set: `golden` fica inteiramente fora do `desenvolvimento`,
    mesmo os alertas de `golden` não selecionados na amostra final (ADR-014) — garante interseção de
    transação vazia por construção, já que a mesma transação nunca aparece em duas contas diferentes."""

    golden: frozenset[str]
    desenvolvimento: frozenset[str]


def particiona_contas(
    conn: sqlite3.Connection, seed: int, *, fracao_suspeitas: float = 0.5, fracao_normais: float = 0.3
) -> ParticaoContas:
    todas_suspeitas = {
        linha[0] for linha in conn.execute("SELECT DISTINCT sender_account FROM transacoes WHERE is_laundering = 1")
    }
    todas_contas = {linha[0] for linha in conn.execute("SELECT DISTINCT sender_account FROM transacoes")}
    todas_normais = todas_contas - todas_suspeitas

    rng = random.Random(seed)
    golden_suspeitas = set(rng.sample(sorted(todas_suspeitas), round(len(todas_suspeitas) * fracao_suspeitas)))
    golden_normais = set(rng.sample(sorted(todas_normais), round(len(todas_normais) * fracao_normais)))
    golden = golden_suspeitas | golden_normais
    return ParticaoContas(golden=frozenset(golden), desenvolvimento=frozenset(todas_contas - golden))


def constroi_estrato_pools(
    db_path: Path,
    regras: AlertRulesConfig,
    mapping: SamlDMapping,
    seed: int,
    *,
    fracao_suspeitas: float = 0.5,
    fracao_normais: float = 0.3,
) -> tuple[dict[str, list[Alert]], list[Alert]]:
    """Devolve (pools por estrato dentro da conta golden, alertas de desenvolvimento). Um alerta cuja conta
    caiu em `desenvolvimento` nunca entra em `pools`, mesmo que fosse elegível a algum estrato; um alerta
    misto (`estrato_de_alerta` -> None) de conta golden é descartado de ambos, nunca reaproveitado."""
    with closing(conecta(db_path)) as conn:
        particao = particiona_contas(conn, seed, fracao_suspeitas=fracao_suspeitas, fracao_normais=fracao_normais)
        rotulos = dict(conn.execute("SELECT transaction_id, laundering_type FROM transacoes"))

    pools: dict[str, list[Alert]] = defaultdict(list)
    desenvolvimento: list[Alert] = []
    for alerta in gera_alertas(db_path, regras):
        if alerta.sender_account not in particao.golden:
            desenvolvimento.append(alerta)
            continue
        estrato = estrato_de_alerta(alerta, rotulos, mapping)
        if estrato is not None:
            pools[estrato].append(alerta)
    return dict(pools), desenvolvimento


def seleciona_golden(
    pools: dict[str, list[Alert]],
    mapping: SamlDMapping,
    seed: int,
    *,
    por_tipologia_critica: int = 30,
    por_tipologia_nao_critica: int = 10,
    total_normais: int = 210,
) -> list[tuple[Alert, str]]:
    rng = random.Random(seed)
    selecionados: list[tuple[Alert, str]] = []

    for rotulo in sorted(mapping.tipologias):
        quota = por_tipologia_critica if mapping.tipologias[rotulo].critica else por_tipologia_nao_critica
        candidatos = sorted(pools.get(rotulo, []), key=lambda a: str(a.alert_id))
        if len(candidatos) < quota:
            raise GoldenSetError(f"{rotulo}: {len(candidatos)} alertas disponíveis na pool golden, quota {quota}")
        for alerta in rng.sample(candidatos, quota):
            selecionados.append((alerta, rotulo))

    disponibilidade_normais = {rotulo: len(pools.get(rotulo, [])) for rotulo in mapping.normais}
    quotas_normais = _distribui_agua(disponibilidade_normais, total_normais)
    for rotulo in sorted(mapping.normais):
        candidatos = sorted(pools.get(rotulo, []), key=lambda a: str(a.alert_id))
        for alerta in rng.sample(candidatos, quotas_normais[rotulo]):
            selecionados.append((alerta, rotulo))

    return selecionados
