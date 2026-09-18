"""Testes do corpus normativo (T1.7, RF-14): chunking por fixture, hash normalizado, MCP-03/MCP-04 e download real."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from aml_guardian.contracts.pipeline import NormChunk
from aml_guardian.norms.chunker import chunk_articles
from aml_guardian.norms.manifest import NormDocSource, derive_corpus_version
from aml_guardian.norms.normalize import normalize_text, text_sha256
from aml_guardian.norms.server import get_norm_passage, search_norms

URL = "https://normativos.bcb.gov.br/Lists/Normativos/Attachments/50905/Circ_3978_v5_P.pdf"

# Fixture no molde real de Circ. 3978/2020 art. 43/44 (parágrafo numerado + incisos sem alínea).
CIRC_FIXTURE = """
Preâmbulo irrelevante do normativo antes do primeiro artigo, sem valor de dispositivo citável.

Art. 43.  As instituições referidas no art. 1º devem implementar procedimentos de
análise das operações e situações selecionadas.
§ 1º  O período para a execução dos procedimentos de análise das operações e
situações selecionadas não pode exceder o prazo de quarenta e cinco dias, contados a partir da
data da seleção da operação ou situação.
§ 2º  A análise mencionada no caput deve ser formalizada em dossiê, independentemente
da comunicação ao Coaf referida no art. 48.
Art. 44.  É vedada:
I - a contratação de terceiros para a realização da análise referida no art. 43; e
II - a realização da análise referida no art. 43 no exterior.
"""

# Fixture no molde real de CC 4.001/2020 art. 1º (caput direto em incisos, incisos com alínea).
CC_FIXTURE = """
Art. 1º  As operações ou as situações descritas a seguir exemplificam indícios de suspeita:
I - situações relacionadas com operações em espécie:
a) depósitos que apresentem atipicidade em relação à atividade econômica do cliente;
b) movimentações em espécie realizadas por clientes cujas atividades usem outros instrumentos;
IV - situações relacionadas com a movimentação de contas de depósito:
a) movimentação de recursos incompatível com o patrimônio do cliente;
"""


class TestChunkArticles:
    def test_circular_produces_expected_article_refs(self):
        chunks = chunk_articles("Circ3978", URL, "v1", CIRC_FIXTURE)
        refs = {chunk.article_ref for chunk in chunks}
        assert refs == {
            "Circ3978/art43/caput",
            "Circ3978/art43/p1",
            "Circ3978/art43/p2",
            "Circ3978/art44/caput",
            "Circ3978/art44/i1",
            "Circ3978/art44/i2",
        }

    def test_paragrafo_1_tem_texto_do_prazo_de_45_dias(self):
        chunks = chunk_articles("Circ3978", URL, "v1", CIRC_FIXTURE)
        p1 = next(chunk for chunk in chunks if chunk.article_ref == "Circ3978/art43/p1")
        assert "quarenta e cinco dias" in p1.text

    def test_carta_circular_produz_incisos_e_alineas(self):
        chunks = chunk_articles("CC4001", URL, "v1", CC_FIXTURE)
        refs = {chunk.article_ref for chunk in chunks}
        assert refs == {
            "CC4001/art1/caput",
            "CC4001/art1/i1",
            "CC4001/art1/i1/a",
            "CC4001/art1/i1/b",
            "CC4001/art1/i4",
            "CC4001/art1/i4/a",
        }

    def test_preambulo_antes_do_primeiro_artigo_e_descartado(self):
        chunks = chunk_articles("Circ3978", URL, "v1", CIRC_FIXTURE)
        assert not any("Preâmbulo irrelevante" in chunk.text for chunk in chunks)

    def test_chunk_e_um_norm_chunk_valido(self):
        chunks = chunk_articles("Circ3978", URL, "v1", CIRC_FIXTURE)
        assert all(isinstance(chunk, NormChunk) for chunk in chunks)
        assert all(chunk.corpus_version == "v1" for chunk in chunks)


class TestNormalizationHash:
    def test_hash_estavel_a_espacamento_diferente(self):
        a = "Texto  com   espaços\nquebrados  e\ttabulação."
        b = "Texto com espaços quebrados e tabulação."
        assert text_sha256(a) == text_sha256(b)

    def test_hash_estavel_a_forma_nfc_vs_nfd(self):
        nfc = "citação"  # "ç" e "ã" já compostos
        nfd = "citaçãao"[:0] + "citação"  # "ç" = c + combining cedilla; "ã" = a + combining til
        assert normalize_text(nfc) == normalize_text(nfd)
        assert text_sha256(nfc) == text_sha256(nfd)

    def test_hash_muda_com_conteudo_diferente(self):
        assert text_sha256("Art. 43.") != text_sha256("Art. 44.")


class TestCorpusVersionReingestao:
    def _doc(self, doc_id: str, sha: str) -> NormDocSource:
        return NormDocSource(
            doc_id=doc_id,
            source_url=URL,
            downloaded_at=datetime.now(UTC),
            doc_sha256=sha,
            local_filename=f"{doc_id}.pdf",
        )

    def test_reingestao_sem_mudanca_mantem_corpus_version(self):
        docs = [self._doc("Circ3978", "a" * 64), self._doc("CC4001", "b" * 64)]
        v1 = derive_corpus_version(docs)
        v2 = derive_corpus_version(list(docs))  # mesmos doc_sha256, nova lista
        assert v1 == v2

    def test_mudanca_de_doc_sha256_muda_corpus_version(self):
        docs = [self._doc("Circ3978", "a" * 64), self._doc("CC4001", "b" * 64)]
        v1 = derive_corpus_version(docs)
        docs[0] = self._doc("Circ3978", "c" * 64)
        v2 = derive_corpus_version(docs)
        assert v1 != v2


class _FakeStore:
    """Store falsa injetada nos servidores MCP-03/MCP-04 para testar sem ChromaDB/FastEmbed real (offline)."""

    def __init__(self, chunks: dict[str, NormChunk]):
        self._chunks = chunks

    def search(self, query: str, top_k: int, corpus_version: str) -> list[dict[str, object]]:
        candidatos = [chunk for chunk in self._chunks.values() if chunk.corpus_version == corpus_version]
        return [{"chunk_id": c.chunk_id, "article_ref": c.article_ref, "score": 0.9} for c in candidatos[:top_k]]

    def get_chunk(self, chunk_id: str, corpus_version: str) -> NormChunk | None:
        chunk = self._chunks.get(chunk_id)
        if chunk is None or chunk.corpus_version != corpus_version:
            return None
        return chunk


def _sample_chunk(corpus_version: str = "v1") -> NormChunk:
    return NormChunk(
        chunk_id="Circ3978:art43/p1:v1",
        doc_id="Circ3978",
        article_ref="Circ3978/art43/p1",
        text="O período para a execução dos procedimentos não pode exceder quarenta e cinco dias.",
        text_sha256=text_sha256("qualquer coisa"),
        corpus_version=corpus_version,
        source_url=URL,
    )


class TestMCP03SearchNorms:
    def test_top_k_9_rejeitado(self):
        store = _FakeStore({})
        result = search_norms("prazo de análise", top_k=9, corpus_version="v1", store=store)
        assert result["error"] == "INVALID_PARAMETER"
        assert result["retryable"] is False

    def test_sucesso_nao_devolve_texto(self):
        chunk = _sample_chunk()
        store = _FakeStore({chunk.chunk_id: chunk})
        result = search_norms("prazo de análise", top_k=8, corpus_version="v1", store=store)
        assert result["status"] == "success"
        for item in result["results"]:
            assert set(item) == {"chunk_id", "article_ref", "score"}


class TestMCP04GetNormPassage:
    def test_chunk_id_de_outra_versao_e_404_logico(self):
        chunk = _sample_chunk(corpus_version="v1")
        store = _FakeStore({chunk.chunk_id: chunk})
        result = get_norm_passage(chunk.chunk_id, corpus_version="v2", store=store)
        assert result["error"] == "NOT_FOUND"
        assert result["retryable"] is False

    def test_chunk_existente_devolve_dt08_completo(self):
        chunk = _sample_chunk()
        store = _FakeStore({chunk.chunk_id: chunk})
        result = get_norm_passage(chunk.chunk_id, corpus_version="v1", store=store)
        assert result["status"] == "success"
        assert result["text"] == chunk.text
        assert result["text_sha256"] == chunk.text_sha256


@pytest.mark.network
def test_download_real_produz_circ3978_art43_p1(tmp_path):
    """RF-14: os dispositivos da seção 3.1 do SPEC.md são encontrados por `article_ref` após download real."""
    from aml_guardian.norms.downloader import download_all
    from aml_guardian.norms.ingest import ingest_corpus
    from aml_guardian.norms.manifest import MANIFEST_FILENAME, write_manifest

    documents = download_all(tmp_path)
    write_manifest(tmp_path / MANIFEST_FILENAME, documents)

    result = ingest_corpus(raw_dir=tmp_path)
    refs = {chunk.article_ref for chunk in result.chunks}
    assert "Circ3978/art43/p1" in refs

    p1 = next(chunk for chunk in result.chunks if chunk.article_ref == "Circ3978/art43/p1")
    assert "quarenta e cinco dias" in p1.text
