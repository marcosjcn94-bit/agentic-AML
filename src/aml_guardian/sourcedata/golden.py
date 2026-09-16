"""Conjunto de desenvolvimento e golden set `v1` (T0.9, `SPEC.md` §8.3, ADR-014).

Particiona `core_sintetico` por conta remetente em pool de desenvolvimento e pool golden, classifica cada
alerta gerado pelo monitoramento legado (T0.8) pela tipologia real do SAML-D das suas transações, e seleciona
uma amostra determinística estratificada (seed) que é congelada em manifesto com hash (`golden_manifest.py`).

Golden set MUST NOT ser usado para calibrar regras de triagem — ajuste usa `alertas_desenvolvimento()`.
"""

from __future__ import annotations

from collections.abc import Mapping


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
