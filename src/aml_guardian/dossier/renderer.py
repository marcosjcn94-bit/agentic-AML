"""Renderização Jinja2 dos templates de dossiê (T1.9, RF-08): nenhum texto livre de LLM, só os campos do DT-11.

`autoescape` desligado de propósito: a saída é markdown/texto puro para o analista, nunca HTML, e todo valor
interpolado vem de um `Dossier` (DT-11) já validado por Pydantic — nenhum dado de fora do perímetro determinístico
(nem prompt, nem resposta de LLM) chega ao template.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from aml_guardian.contracts.pipeline import Dossier, DossierType

TEMPLATES_DIR = Path(__file__).parent / "templates"

_ENV = Environment(  # noqa: S701 - saída é markdown/texto, não HTML; conteúdo vem só do DT-11 já validado
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
)

_TEMPLATE_BY_TYPE = {DossierType.COS: "cos.md.j2", DossierType.ARQUIVAMENTO: "arquivamento.md.j2"}


def render_dossier(dossier: Dossier) -> str:
    """Renderiza o dossiê (DT-11) pelo template Jinja2 do seu `type`; nenhum texto livre vem do LLM (RF-08)."""
    template = _ENV.get_template(_TEMPLATE_BY_TYPE[dossier.type])
    return template.render(dossier=dossier)
