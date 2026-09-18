"""T1.13 — Avaliador inicial (`pytest -k evaluate`): relatório sobre amostra sintética, `SPEC.md` §10."""

from __future__ import annotations

import json

import pytest

from aml_guardian.config.triage import load_triage_rules
from aml_guardian.eval.gates import avalia_gates, percentil
from aml_guardian.eval.latency import mede_fluxo_investigar
from aml_guardian.eval.report import escreve_relatorio, monta_relatorio
from aml_guardian.sourcedata.mapping import load_saml_d_mapping

_MOCK_RESPONSE = json.dumps({"t": "Structuring", "c": 0.8, "r": "COMUNICAR", "e": [3]})


@pytest.fixture(scope="module")
def relatorio_amostra(tmp_path_factory) -> dict[str, object]:
    tmp = tmp_path_factory.mktemp("eval-amostra")
    amostras, auditoria_valida = mede_fluxo_investigar(2, tmp, mock_response=_MOCK_RESPONSE)
    return monta_relatorio(
        amostras,
        auditoria_valida,
        rules_version=load_triage_rules().rules_version,
        mapping_version=load_saml_d_mapping().mapping_version,
    )


class TestRelatorioSobreAmostraSintetica:
    def test_amostra_tem_o_tamanho_pedido_e_chega_a_draft_ready(self, relatorio_amostra):
        assert relatorio_amostra["amostra"]["tamanho"] == 2
        assert relatorio_amostra["amostra"]["states_finais"] == ["DRAFT_READY", "DRAFT_READY"]

    def test_versoes_gravadas(self, relatorio_amostra):
        versoes = relatorio_amostra["versoes"]
        for chave in ("rules_version", "mapping_version", "features_version", "prompt_version", "corpus_version"):
            assert versoes[chave] is not None

    def test_latencia_medida_e_positiva(self, relatorio_amostra):
        latencia = relatorio_amostra["latencia_fluxo_investigar_ms"]
        assert latencia["p50"] is not None
        assert latencia["p95"] is not None
        assert latencia["p50"] > 0


class TestGateNaoImplementadoNuncaAprovado:
    def test_gates_nao_medidos_tem_aprovado_none(self, relatorio_amostra):
        nao_medidos = [g for g in relatorio_amostra["gates"] if g["status"] == "não medida"]
        assert len(nao_medidos) >= 1
        for gate in nao_medidos:
            assert gate["aprovado"] is None
            assert gate["nota"]

    def test_todos_os_nove_gates_do_spec_presentes(self, relatorio_amostra):
        metricas = {g["metrica"] for g in relatorio_amostra["gates"]}
        assert metricas == {
            "Recall crítico",
            "Grounding",
            "Redução de falsos positivos",
            "Velocidade",
            "Redução de tokens",
            "Latência",
            "Prazo interno",
            "Privacidade",
            "Integridade da auditoria",
        }

    def test_gate_de_latencia_medido_e_aprovado_na_amostra(self, relatorio_amostra):
        gate_latencia = next(g for g in relatorio_amostra["gates"] if g["metrica"] == "Latência")
        assert gate_latencia["status"] == "medida"
        assert gate_latencia["aprovado"] is True  # mock: bem abaixo de 20s


class TestRelatorioSemDadoPessoal:
    def test_relatorio_nao_carrega_dado_pessoal(self, relatorio_amostra):
        bruto = json.dumps(relatorio_amostra).lower()
        for termo in ("cpf_cnpj", "sender_customer", "amostra avaliador ltda"):
            assert termo not in bruto

    def test_arquivos_gravados_sem_dado_pessoal(self, relatorio_amostra, tmp_path):
        json_path, md_path = escreve_relatorio(relatorio_amostra, tmp_path)
        assert json_path.exists()
        assert md_path.exists()
        conteudo = (json_path.read_text(encoding="utf-8") + md_path.read_text(encoding="utf-8")).lower()
        assert "cpf_cnpj" not in conteudo
        assert "amostra avaliador ltda" not in conteudo


class TestAmostraVaziaNaoQuebra:
    """Achado do python-reviewer (T1.13): `--sample-size 0`/lista vazia levava a `ZeroDivisionError`/`IndexError`."""

    def test_percentil_com_lista_vazia_levanta_value_error(self):
        with pytest.raises(ValueError, match="ao menos um valor"):
            percentil([], 95)

    def test_avalia_gates_com_amostra_vazia_levanta_value_error(self):
        from aml_guardian.config.baseline import load_baseline

        with pytest.raises(ValueError, match="ao menos uma amostra"):
            avalia_gates([], load_baseline(), auditoria_valida=True)
