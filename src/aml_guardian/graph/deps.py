"""Dependências injetáveis dos nós do grafo (T1.10): mesmos protocolos já usados pelos módulos de T1.4-T1.9.

`corpus_version` é obrigatório porque nenhum outro módulo hoje expõe "a `corpus_version` vigente" em runtime —
quem monta o grafo decide qual versão está ativa (T1.7 `ingest_corpus().corpus_version`, ou um valor fixo em
teste). As demais dependências são opcionais: `None` deixa cada módulo carregar sua configuração versionada
padrão, exatamente como já fazem `run_triage`, `run_investigation` e `select_citations`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from aml_guardian.config.litellm import LiteLLMConfig
from aml_guardian.config.retrieval import RetrievalConfig
from aml_guardian.config.triage import TriageRulesConfig
from aml_guardian.features.catalog import HistoryFetcher
from aml_guardian.investigation.litellm_client import ContadorChamadas
from aml_guardian.mcp_servers.server import check_restriction_lists, get_customer_history
from aml_guardian.norms.server import get_norm_passage, search_norms
from aml_guardian.retrieval.query import NormSearcher
from aml_guardian.retrieval.selection import NormPassageGetter
from aml_guardian.sourcedata.mapping import SamlDMapping
from aml_guardian.triage.engine import RestrictionChecker


@dataclass
class GraphDeps:
    """Feixe de dependências repassado aos nós; só `corpus_version` é obrigatório."""

    corpus_version: str
    db_path: Path | None = None
    triage_rules: TriageRulesConfig | None = None
    litellm_config: LiteLLMConfig | None = None
    saml_mapping: SamlDMapping | None = None
    retrieval_cfg: RetrievalConfig | None = None
    restriction_checker: RestrictionChecker = check_restriction_lists
    history_fetcher: HistoryFetcher = get_customer_history
    searcher: NormSearcher = search_norms
    passage_getter: NormPassageGetter = get_norm_passage
    contador: ContadorChamadas | None = None
    model_overrides: dict[str, object] = field(default_factory=dict)
