"""Montador do prompt da Investigação (T1.6, RF-05): teto de 300 tokens de entrada (AGENTS.md §4.1).

O montador conta tokens com o tokenizador do modelo via LiteLLM (`litellm.token_counter`) antes de qualquer
chamada. Acima do teto, remove as contrapartes F14+ de menor `brl`, uma por vez (empate: maior `feature_id`
sai primeiro); F01-F13 nunca são removidas. Ainda acima do teto sem F14+ para remover: quem chama decide
`NEEDS_HUMAN` sem chamar o modelo (AGENTS.md §4.1).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

import litellm

from aml_guardian.contracts.ingestion import SanitizedAlert
from aml_guardian.contracts.pipeline import Feature
from aml_guardian.investigation.contract import INVESTIGATION_INSTRUCTIONS, bloco_alerta

MAX_PROMPT_TOKENS = 300
_BRL_NA_LINHA = re.compile(r"brl=(-?\d+)")


@dataclass(frozen=True)
class PromptMontado:
    """Resultado do montador: prompt final, features que sobraram, tokens contados e o que foi descartado."""

    texto: str
    features: list[Feature]
    tokens: int
    descartadas: list[str] = field(default_factory=list)

    @property
    def dentro_do_teto(self) -> bool:
        return self.tokens <= MAX_PROMPT_TOKENS


def _numero(feature: Feature) -> int:
    return int(feature.feature_id[1:])


def _brl(feature: Feature) -> Decimal:
    """`brl` embutido no valor de F14+ (`in=.. out=.. brl=NN`); F01-F13 nunca chegam aqui (não são removíveis)."""
    achado = _BRL_NA_LINHA.search(feature.value) if isinstance(feature.value, str) else None
    return Decimal(achado.group(1)) if achado else Decimal(0)


def montar_prompt(
    model: str, sanitized_alert: SanitizedAlert, detectores_disparados: list[str], features: list[Feature]
) -> PromptMontado:
    """Monta o prompt e aplica o teto de 300 tokens removendo F14+ até caber ou esgotar (AGENTS.md §4.1)."""
    presentes = list(features)
    descartadas: list[str] = []
    while True:
        texto = INVESTIGATION_INSTRUCTIONS + bloco_alerta(sanitized_alert, detectores_disparados, presentes)
        tokens = litellm.token_counter(model=model, text=texto)
        if tokens <= MAX_PROMPT_TOKENS:
            return PromptMontado(texto=texto, features=presentes, tokens=tokens, descartadas=descartadas)
        removiveis = [f for f in presentes if _numero(f) >= 14]
        if not removiveis:
            return PromptMontado(texto=texto, features=presentes, tokens=tokens, descartadas=descartadas)
        # Menor `brl` primeiro; empate desfeito pelo maior `feature_id` (AGENTS.md §4.1).
        pior = min(removiveis, key=lambda f: (_brl(f), -_numero(f)))
        presentes = [f for f in presentes if f.feature_id != pior.feature_id]
        descartadas.append(pior.feature_id)
