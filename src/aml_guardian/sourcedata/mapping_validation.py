"""Valida referências normativas curadas contra o corpus materializado.

Uma tipologia sem curadoria continua sem citação normativa. A validação só
aceita referências que já existam no corpus; ela não tenta inferir artigos.
"""

from __future__ import annotations

from aml_guardian.sourcedata.mapping import SamlDMapping


def validate_curated_article_refs(mapping: SamlDMapping, available_refs: set[str]) -> list[str]:
    """Devolve erros das referências preenchidas que não existem no corpus."""
    errors: list[str] = []
    for label, typology in mapping.tipologias.items():
        for article_ref in typology.article_ref:
            if article_ref not in available_refs:
                errors.append(f"{label}: article_ref ausente no corpus: {article_ref}")
    return errors


def curated_typology_labels(mapping: SamlDMapping) -> frozenset[str]:
    """Retorna apenas rótulos com aplicabilidade e referências curadas."""
    return frozenset(
        label
        for label, typology in mapping.tipologias.items()
        if typology.article_ref and typology.applicability is not None
    )
