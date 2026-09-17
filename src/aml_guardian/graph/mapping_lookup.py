"""Enquadramento normativo de uma `Typology` no mapeamento SAML-D → CC 4.001/2020 (T1.10).

Só um `dict` reverso sobre `SamlDMapping.tipologias` (T0.6/T1.7): não decide nada, não normaliza nada — a
Recuperação e a Seleção (T1.8) já fazem isso a partir do enquadramento que este módulo localiza.
"""

from __future__ import annotations

from aml_guardian.contracts.pipeline import Typology
from aml_guardian.sourcedata.mapping import SamlDMapping, Tipologia


def enquadramento_por_typology(mapping: SamlDMapping, typology: Typology) -> Tipologia | None:
    """Enquadramento cujo `typology` bate com a hipótese da Investigação; `None` se `NENHUMA` ou sem mapeamento."""
    for item in mapping.tipologias.values():
        if item.typology is typology:
            return item
    return None
