"""Contratos de normas e dossiê (DT-08 a DT-11; SPEC.md §8.2, RF-06 a RF-09; T0.3).

Dados sintéticos; texto normativo fictício e hash calculado em tempo de execução.
"""

from __future__ import annotations

import copy
import hashlib
from typing import Any

import pytest
from pydantic import ValidationError

from aml_guardian.contracts.pipeline import Citation, Dossier, DossierType, NormChunk, ReviewVerdict

ALERT_ID = "8f5c2a1e-3b7d-4c9a-9e21-6a0f4d2b7c11"
TEXT = "Texto normativo sintético do dispositivo usado apenas em teste."

CHUNK: dict[str, Any] = {
    "chunk_id": "chunk-0001",
    "doc_id": "circ-3978-2020",
    "article_ref": "Circ3978/art43/p1",
    "text": TEXT,
    "text_sha256": hashlib.sha256(TEXT.encode()).hexdigest(),
    "corpus_version": "corpus-0001",
    "source_url": "https://www.bcb.gov.br/api/conteudo/app/normativos/exibenormativo?p1=Circular&p2=3978",
}

CITATION: dict[str, Any] = {
    "chunk_id": "chunk-0001",
    "article_ref": "Circ3978/art43/p1",
    "quoted_text": TEXT,
    "applicability": "Texto curado sintético de aplicabilidade.",
}

VERDICT: dict[str, Any] = {
    "verified_citations": [CITATION],
    "rejected_citations": [{"chunk_id": "chunk-0002", "reason": "text_sha256 divergente"}],
    "grounding_raw_ratio": 0.5,
}

COS_DOSSIER: dict[str, Any] = {
    "dossier_id": "0b7e6f1a-2c3d-4e5f-8a9b-1c2d3e4f5a6b",
    "alert_id": ALERT_ID,
    "type": "COS",
    "summary": "Minuta sintética gerada por template.",
    "typology": "Structuring",
    "cc4001_incisos": ["I", "IV"],
    "evidence": [{"feature_id": "F03", "name": "abaixo_limiar", "value": 9, "transaction_ids": ["tx-0001"]}],
    "citations": [CITATION],
    "recommendation": "COMUNICAR",
    "ai_generated_fields": ["typology_hypothesis", "confidence", "recommendation", "evidence_feature_ids"],
    "deadlines": {
        "selecao_em": "2026-09-15T13:00:00Z",
        "prazo_interno": "2026-09-20T13:00:00Z",
        "prazo_regulatorio_analise": "2026-10-30T13:00:00Z",
    },
    "versions": {
        "rules": 1,
        "corpus": "corpus-0001",
        "mapping": 1,
        "features": 1,
        "prompt": "v1",
        "model": "investigador",
    },
    "status": "DRAFT_READY",
}


def _copy(payload: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(payload)


def _triage_archive() -> dict[str, Any]:
    """Dossiê do caminho `PROPOR_ARQUIVAMENTO`: só DT-06, sem nó LLM, recuperação nem mapeamento."""
    payload = _copy(COS_DOSSIER)
    payload.update(
        type="ARQUIVAMENTO",
        typology=None,
        cc4001_incisos=[],
        evidence=[],
        citations=[],
        recommendation="ARQUIVAR",
        ai_generated_fields=[],
    )
    payload["versions"] = {"rules": 1, "corpus": None, "mapping": None, "features": None, "prompt": None, "model": None}
    return payload


# DT-08 ------------------------------------------------------------------------


def test_dt_investigacao_chunk_valido() -> None:
    assert NormChunk.model_validate(_copy(CHUNK)).text == TEXT


@pytest.mark.parametrize("digest", ["a" * 63, "A" * 64, "g" * 64])
def test_dt_investigacao_chunk_sha256_invalido(digest: str) -> None:
    payload = _copy(CHUNK)
    payload["text_sha256"] = digest
    with pytest.raises(ValidationError):
        NormChunk.model_validate(payload)


def test_dt_investigacao_chunk_source_url_invalida() -> None:
    payload = _copy(CHUNK)
    payload["source_url"] = "bcb.gov.br/normativo"
    with pytest.raises(ValidationError):
        NormChunk.model_validate(payload)


# DT-09 ------------------------------------------------------------------------


def test_dt_investigacao_applicability_300_caracteres_aceita() -> None:
    payload = _copy(CITATION)
    payload["applicability"] = "a" * 300
    assert len(Citation.model_validate(payload).applicability) == 300


def test_dt_investigacao_applicability_301_caracteres_rejeitada() -> None:
    payload = _copy(CITATION)
    payload["applicability"] = "a" * 301
    with pytest.raises(ValidationError):
        Citation.model_validate(payload)


@pytest.mark.parametrize("field", ["quoted_text", "applicability"])
@pytest.mark.parametrize("value", ["", "   "])
def test_dt_investigacao_citacao_texto_vazio_rejeitado(field: str, value: str) -> None:
    payload = _copy(CITATION)
    payload[field] = value
    with pytest.raises(ValidationError):
        Citation.model_validate(payload)


def test_dt_investigacao_citacao_preserva_texto_copiado() -> None:
    payload = _copy(CITATION)
    payload["quoted_text"] = f" {TEXT}\n"
    assert Citation.model_validate(payload).quoted_text == f" {TEXT}\n"


# DT-10 ------------------------------------------------------------------------


def test_dt_investigacao_veredito_valido() -> None:
    verdict = ReviewVerdict.model_validate(_copy(VERDICT))
    assert verdict.rejected_citations[0].chunk_id == "chunk-0002"


@pytest.mark.parametrize("ratio", [1.01, -0.1, True])
def test_dt_investigacao_veredito_ratio_invalido(ratio: object) -> None:
    payload = _copy(VERDICT)
    payload["grounding_raw_ratio"] = ratio
    with pytest.raises(ValidationError):
        ReviewVerdict.model_validate(payload)


def test_dt_investigacao_veredito_chunk_verificado_e_rejeitado() -> None:
    payload = _copy(VERDICT)
    payload["rejected_citations"][0]["chunk_id"] = "chunk-0001"
    with pytest.raises(ValidationError, match="chunk-0001"):
        ReviewVerdict.model_validate(payload)


# DT-11 ------------------------------------------------------------------------


def test_dt_investigacao_dossie_cos_valido() -> None:
    dossier = Dossier.model_validate(_copy(COS_DOSSIER))
    assert dossier.type is DossierType.COS
    assert Dossier.model_validate_json(dossier.model_dump_json()) == dossier


def test_dt_investigacao_dossie_arquivamento_da_triagem_valido() -> None:
    dossier = Dossier.model_validate(_triage_archive())
    assert dossier.typology is None
    assert dossier.versions.prompt is None


def test_dt_investigacao_dossie_enum_tipo_do_spec() -> None:
    assert {t.value for t in DossierType} == {"COS", "ARQUIVAMENTO"}


def test_dt_investigacao_dossie_tipo_fora_do_enum() -> None:
    payload = _copy(COS_DOSSIER)
    payload["type"] = "RIF"
    with pytest.raises(ValidationError):
        Dossier.model_validate(payload)


@pytest.mark.parametrize("field", list(COS_DOSSIER))
def test_dt_investigacao_dossie_sem_campo_obrigatorio(field: str) -> None:
    payload = _copy(COS_DOSSIER)
    del payload[field]
    with pytest.raises(ValidationError):
        Dossier.model_validate(payload)


@pytest.mark.parametrize("key", ["rules", "corpus", "mapping", "features", "prompt", "model"])
def test_dt_investigacao_dossie_versions_sem_chave(key: str) -> None:
    payload = _copy(COS_DOSSIER)
    del payload["versions"][key]
    with pytest.raises(ValidationError):
        Dossier.model_validate(payload)


@pytest.mark.parametrize("key", ["selecao_em", "prazo_interno", "prazo_regulatorio_analise"])
def test_dt_investigacao_dossie_deadlines_sem_chave(key: str) -> None:
    payload = _copy(COS_DOSSIER)
    del payload["deadlines"][key]
    with pytest.raises(ValidationError):
        Dossier.model_validate(payload)


def test_dt_investigacao_dossie_prazos_fora_de_ordem() -> None:
    payload = _copy(COS_DOSSIER)
    payload["deadlines"]["prazo_interno"] = "2026-09-14T13:00:00Z"
    with pytest.raises(ValidationError):
        Dossier.model_validate(payload)


@pytest.mark.parametrize(
    ("dossier_type", "recommendation"),
    [("COS", "ARQUIVAR"), ("ARQUIVAMENTO", "COMUNICAR"), ("COS", "INCONCLUSIVO"), ("ARQUIVAMENTO", "INCONCLUSIVO")],
)
def test_dt_investigacao_dossie_tipo_incoerente_com_recomendacao(dossier_type: str, recommendation: str) -> None:
    payload = _copy(COS_DOSSIER)
    payload.update(type=dossier_type, recommendation=recommendation)
    with pytest.raises(ValidationError):
        Dossier.model_validate(payload)


def test_dt_investigacao_dossie_cos_sem_citacao_rejeitado() -> None:
    payload = _copy(COS_DOSSIER)
    payload["citations"] = []
    with pytest.raises(ValidationError, match="RF-07"):
        Dossier.model_validate(payload)


def test_dt_investigacao_dossie_quatro_evidencias_rejeitadas() -> None:
    payload = _copy(COS_DOSSIER)
    feature = payload["evidence"][0]
    payload["evidence"] = [{**feature, "feature_id": f"F0{n}"} for n in range(1, 5)]
    with pytest.raises(ValidationError):
        Dossier.model_validate(payload)


def test_dt_investigacao_dossie_ai_generated_fields_parcial_rejeitado() -> None:
    payload = _copy(COS_DOSSIER)
    payload["ai_generated_fields"] = ["typology_hypothesis", "confidence"]
    with pytest.raises(ValidationError):
        Dossier.model_validate(payload)


@pytest.mark.parametrize("key", ["corpus", "mapping", "features", "prompt", "model"])
def test_dt_investigacao_dossie_investigado_sem_versao(key: str) -> None:
    payload = _copy(COS_DOSSIER)
    payload["versions"][key] = None
    with pytest.raises(ValidationError):
        Dossier.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("typology", "Structuring"),
        ("cc4001_incisos", ["I"]),
        ("evidence", COS_DOSSIER["evidence"]),
        ("citations", [CITATION]),
    ],
)
def test_dt_investigacao_dossie_triagem_com_campo_de_investigacao(field: str, value: object) -> None:
    payload = _triage_archive()
    payload[field] = copy.deepcopy(value)
    with pytest.raises(ValidationError):
        Dossier.model_validate(payload)


@pytest.mark.parametrize("status", ["NEEDS_HUMAN", "REVIEWING", "RECEIVED"])
def test_dt_investigacao_dossie_status_invalido(status: str) -> None:
    payload = _copy(COS_DOSSIER)
    payload["status"] = status
    with pytest.raises(ValidationError):
        Dossier.model_validate(payload)


@pytest.mark.parametrize("inciso", ["iv", "4", "IV-d", ""])
def test_dt_investigacao_dossie_inciso_fora_do_formato(inciso: str) -> None:
    payload = _copy(COS_DOSSIER)
    payload["cc4001_incisos"] = [inciso]
    with pytest.raises(ValidationError):
        Dossier.model_validate(payload)
