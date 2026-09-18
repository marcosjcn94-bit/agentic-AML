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

from aml_guardian.config.alert_rules import AlertRulesConfig, load_alert_rules
from aml_guardian.contracts.ingestion import Alert
from aml_guardian.sourcedata.alert_generator import gera_alertas
from aml_guardian.sourcedata.core_db import CORE_DB_PATH, conecta, conteudo_sha256
from aml_guardian.sourcedata.golden_manifest import GoldenManifest, GoldenSetError, constroi_manifesto
from aml_guardian.sourcedata.mapping import SamlDMapping, load_saml_d_mapping

SEED_PADRAO = 20260916
FRACAO_GOLDEN_SUSPEITAS = 0.5
FRACAO_GOLDEN_NORMAIS = 0.3
POR_TIPOLOGIA_CRITICA = 30
POR_TIPOLOGIA_NAO_CRITICA = 10
TOTAL_NORMAIS = 210


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
) -> tuple[list[tuple[Alert, str]], dict[str, int]]:
    """Devolve (selecionados, disponibilidade_por_estrato) — a disponibilidade é o tamanho da pool golden de
    cada estrato ANTES da amostragem, para o manifesto permitir reponderação por probabilidade inversa de
    seleção (ADR-014)."""
    rng = random.Random(seed)
    selecionados: list[tuple[Alert, str]] = []
    disponibilidade_por_estrato: dict[str, int] = {}

    for rotulo in sorted(mapping.tipologias):
        quota = por_tipologia_critica if mapping.tipologias[rotulo].critica else por_tipologia_nao_critica
        candidatos = sorted(pools.get(rotulo, []), key=lambda a: str(a.alert_id))
        disponibilidade_por_estrato[rotulo] = len(candidatos)
        if len(candidatos) < quota:
            raise GoldenSetError(f"{rotulo}: {len(candidatos)} alertas disponíveis na pool golden, quota {quota}")
        for alerta in rng.sample(candidatos, quota):
            selecionados.append((alerta, rotulo))

    disponibilidade_normais = {rotulo: len(pools.get(rotulo, [])) for rotulo in mapping.normais}
    disponibilidade_por_estrato.update(disponibilidade_normais)
    quotas_normais = _distribui_agua(disponibilidade_normais, total_normais)
    for rotulo in sorted(mapping.normais):
        candidatos = sorted(pools.get(rotulo, []), key=lambda a: str(a.alert_id))
        for alerta in rng.sample(candidatos, quotas_normais[rotulo]):
            selecionados.append((alerta, rotulo))

    return selecionados, disponibilidade_por_estrato


def constroi_golden(
    db_path: Path | None = None,
    regras: AlertRulesConfig | None = None,
    mapping: SamlDMapping | None = None,
    seed: int = SEED_PADRAO,
    *,
    fracao_suspeitas: float = FRACAO_GOLDEN_SUSPEITAS,
    fracao_normais: float = FRACAO_GOLDEN_NORMAIS,
    por_tipologia_critica: int = POR_TIPOLOGIA_CRITICA,
    por_tipologia_nao_critica: int = POR_TIPOLOGIA_NAO_CRITICA,
    total_normais: int = TOTAL_NORMAIS,
) -> tuple[GoldenManifest, list[tuple[Alert, str]], list[Alert]]:
    """Orquestra a construção do golden set `v1`: particiona contas, classifica estratos, amostra as quotas e
    congela o manifesto com hash (ADR-014). Devolve (manifesto, selecionados, desenvolvimento) para o chamador
    decidir entre gravar em disco (`grava_golden`) ou apenas inspecionar."""
    caminho = db_path or CORE_DB_PATH
    config = regras or load_alert_rules()
    mapa = mapping or load_saml_d_mapping()

    pools, desenvolvimento = constroi_estrato_pools(
        caminho, config, mapa, seed, fracao_suspeitas=fracao_suspeitas, fracao_normais=fracao_normais
    )
    selecionados, disponibilidade_por_estrato = seleciona_golden(
        pools, mapa, seed,
        por_tipologia_critica=por_tipologia_critica,
        por_tipologia_nao_critica=por_tipologia_nao_critica,
        total_normais=total_normais,
    )
    with closing(conecta(caminho)) as conn:
        core_sha = conteudo_sha256(conn)
    manifesto = constroi_manifesto(
        selecionados,
        core_sintetico_sha256=core_sha,
        alert_rules_version=config.alert_rules_version,
        mapping_version=mapa.mapping_version,
        seed=seed,
        disponibilidade_por_estrato=disponibilidade_por_estrato,
    )
    return manifesto, selecionados, desenvolvimento


def alertas_desenvolvimento(
    db_path: Path | None = None,
    regras: AlertRulesConfig | None = None,
    mapping: SamlDMapping | None = None,
    seed: int = SEED_PADRAO,
    *,
    fracao_suspeitas: float = FRACAO_GOLDEN_SUSPEITAS,
    fracao_normais: float = FRACAO_GOLDEN_NORMAIS,
) -> list[Alert]:
    """Conjunto de desenvolvimento (disjunto do golden por conta) para calibrar regras de triagem (T1.4).
    Golden set MUST NOT ser usado para esse ajuste (`SPEC.md` §8.3)."""
    caminho = db_path or CORE_DB_PATH
    config = regras or load_alert_rules()
    mapa = mapping or load_saml_d_mapping()
    _, desenvolvimento = constroi_estrato_pools(
        caminho, config, mapa, seed, fracao_suspeitas=fracao_suspeitas, fracao_normais=fracao_normais
    )
    return desenvolvimento
