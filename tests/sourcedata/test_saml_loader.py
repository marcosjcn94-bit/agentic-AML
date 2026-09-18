"""Loader do SAML-D e mapeamento para a CC 4.001/2020 (T0.6): SPEC.md §3.2 e §8.3.

Nenhum caso toca o CSV real (não versionado, CC BY-NC-SA 4.0): o CSV é gerado no próprio teste.
Os casos inválidos do mapeamento partem do arquivo versionado, alteram um único ponto e gravam em `tmp_path`.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from aml_guardian.config import ConfigError
from aml_guardian.contracts.pipeline import Typology
from aml_guardian.sourcedata import (
    CRITICAS_ESPERADAS,
    MAPPINGS_DIR,
    SAML_D_MAPPING_FILE,
    SamlLoaderError,
    iter_transactions,
    load_saml_d_mapping,
    read_header,
    validate_file,
)

COLUNAS = (
    "Time",
    "Date",
    "Sender_account",
    "Receiver_account",
    "Amount",
    "Payment_currency",
    "Received_currency",
    "Sender_bank_location",
    "Receiver_bank_location",
    "Payment_type",
    "Is_laundering",
    "Laundering_type",
)
NORMAL = (
    "10:35:19",
    "2022-10-07",
    "8724731955",
    "2769355426",
    "1459.15",
    "UK pounds",
    "UK pounds",
    "UK",
    "UK",
    "Cash Deposit",
    "0",
    "Normal_Cash_Deposits",
)
SUSPEITA = (
    "11:02:41",
    "2022-10-08",
    "8724731955",
    "2769355426",
    "9500.00",
    "UK pounds",
    "UK pounds",
    "UK",
    "UK",
    "Cash Deposit",
    "1",
    "Structuring",
)

CRITICAS_SPEC = {
    "Deposit-Send",
    "Structuring",
    "Smurfing",
    "Layered_Fan_In",
    "Layered_Fan_Out",
    "Stacked Bipartite",
}


def _csv(tmp_path: Path, linhas: tuple[tuple[str, ...], ...], colunas: tuple[str, ...] = COLUNAS) -> Path:
    destino = tmp_path / "saml.csv"
    corpo = [",".join(colunas), *(",".join(linha) for linha in linhas)]
    destino.write_text("\n".join(corpo) + "\n", encoding="utf-8")
    return destino


def _raw() -> dict[str, Any]:
    return copy.deepcopy(yaml.safe_load((MAPPINGS_DIR / SAML_D_MAPPING_FILE).read_text(encoding="utf-8")))


def _mapping(tmp_path: Path, dados: dict[str, Any]) -> Path:
    destino = tmp_path / SAML_D_MAPPING_FILE
    destino.write_text(yaml.safe_dump(dados, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return destino


@pytest.fixture(scope="module")
def mapeamento():
    return load_saml_d_mapping()


# --- Mapeamento versionado (SPEC.md §3.2) ---


def test_mapeamento_versionado_carrega(mapeamento):
    # mapping_version 2 (T1.8): article_ref/applicability curados para Structuring (lote3-brief.md Ask First).
    assert mapeamento.mapping_version == 2
    assert len(mapeamento.tipologias) == 17
    assert len(mapeamento.normais) == 11


def test_mapeamento_tem_as_seis_criticas_do_spec(mapeamento):
    criticas = {rotulo for rotulo, item in mapeamento.tipologias.items() if item.critica}
    assert criticas == CRITICAS_SPEC
    assert len(criticas) == CRITICAS_ESPERADAS


def test_mapeamento_cobre_todo_o_enum_typology(mapeamento):
    esperado = {opcao for opcao in Typology if opcao is not Typology.NENHUMA}
    assert {item.typology for item in mapeamento.tipologias.values()} == esperado


def test_enquadramentos_da_tabela_do_spec(mapeamento):
    assert mapeamento.tipologias["Deposit-Send"].incisos == ["IX"]
    assert mapeamento.tipologias["Structuring"].incisos == ["I", "IV"]
    assert mapeamento.tipologias["Structuring"].alineas == ["d", "e", "k"]
    assert mapeamento.tipologias["Smurfing"].alineas == ["d", "e", "f", "l", "m"]
    assert mapeamento.tipologias["Over-Invoicing"].incisos == ["X"]
    assert mapeamento.tipologias["Cash_Withdrawal"].incisos == ["I"]


def test_selecao_de_trechos_fica_vazia_ate_t18(mapeamento):
    """T1.8 curou article_ref/applicability só para Structuring (tipologia do alerta E2E); as demais seguem vazias."""
    outras = {rotulo: item for rotulo, item in mapeamento.tipologias.items() if rotulo != "Structuring"}
    assert all(item.article_ref == [] for item in outras.values())
    assert all(item.applicability is None for item in outras.values())

    structuring = mapeamento.tipologias["Structuring"]
    assert structuring.article_ref == ["CC4001/art1/i1/d", "CC4001/art1/i1/e", "CC4001/art1/i1/k", "CC4001/art1/i4"]
    assert structuring.applicability is not None


def test_rotulos_normais_nao_tem_enquadramento(mapeamento):
    assert "Normal_Cash_Deposits" in mapeamento.rotulos
    assert not mapeamento.is_suspeito("Normal_Cash_Deposits")
    assert mapeamento.is_suspeito("Structuring")


def test_mapeamento_sem_mapping_version_falha(tmp_path):
    dados = _raw()
    del dados["mapping_version"]
    with pytest.raises(ConfigError, match="mapping_version"):
        load_saml_d_mapping(_mapping(tmp_path, dados))


def test_mapeamento_com_critica_de_tipo_errado_falha(tmp_path):
    dados = _raw()
    dados["tipologias"]["Structuring"]["critica"] = "sim"
    with pytest.raises(ConfigError, match="critica"):
        load_saml_d_mapping(_mapping(tmp_path, dados))


def test_mapeamento_com_cinco_criticas_falha(tmp_path):
    dados = _raw()
    dados["tipologias"]["Smurfing"]["critica"] = False
    with pytest.raises(ConfigError, match=f"5 críticas; a tabela do SPEC.md §3.2 define {CRITICAS_ESPERADAS}"):
        load_saml_d_mapping(_mapping(tmp_path, dados))


def test_mapeamento_sem_uma_tipologia_do_enum_falha(tmp_path):
    dados = _raw()
    del dados["tipologias"]["Cycle"]
    with pytest.raises(ConfigError, match="sem rótulo do SAML-D para"):
        load_saml_d_mapping(_mapping(tmp_path, dados))


def test_mapeamento_com_rotulo_em_tipologias_e_normais_falha(tmp_path):
    dados = _raw()
    dados["normais"].append("Structuring")
    with pytest.raises(ConfigError, match="também listados em tipologias"):
        load_saml_d_mapping(_mapping(tmp_path, dados))


def test_mapeamento_com_applicability_vazia_falha(tmp_path):
    dados = _raw()
    dados["tipologias"]["Structuring"]["applicability"] = ""
    with pytest.raises(ConfigError, match="applicability"):
        load_saml_d_mapping(_mapping(tmp_path, dados))


# --- Cabeçalho do CSV (SPEC.md §8.3) ---


def test_coluna_renomeada_falha_citando_a_coluna(tmp_path, mapeamento):
    colunas = tuple("Sender_acc" if nome == "Sender_account" else nome for nome in COLUNAS)
    caminho = _csv(tmp_path, (NORMAL,), colunas)
    with pytest.raises(SamlLoaderError) as erro:
        list(iter_transactions(caminho, mapeamento))
    mensagem = str(erro.value)
    assert "Sender_account" in mensagem
    assert "Sender_acc" in mensagem


def test_nomes_alternativos_do_artigo_de_origem_sao_aceitos(tmp_path, mapeamento):
    colunas = tuple({"Is_laundering": "Is_Suspicious", "Laundering_type": "Type"}.get(nome, nome) for nome in COLUNAS)
    caminho = _csv(tmp_path, (NORMAL, SUSPEITA), colunas)
    cabecalho = read_header(caminho)
    assert (cabecalho.flag_column, cabecalho.type_column) == ("Is_Suspicious", "Type")
    assert len(list(iter_transactions(caminho, mapeamento))) == 2


def test_cabecalho_com_as_duas_alternativas_falha(tmp_path):
    caminho = _csv(tmp_path, (), (*COLUNAS, "Type"))
    with pytest.raises(SamlLoaderError, match="ambíguas"):
        read_header(caminho)


def test_coluna_extra_falha_citando_a_coluna(tmp_path):
    caminho = _csv(tmp_path, (), (*COLUNAS, "Risco"))
    with pytest.raises(SamlLoaderError, match=r"não prevista\(s\): \['Risco'\]"):
        read_header(caminho)


def test_arquivo_vazio_falha(tmp_path):
    caminho = tmp_path / "saml.csv"
    caminho.write_text("", encoding="utf-8")
    with pytest.raises(SamlLoaderError, match="sem cabeçalho"):
        read_header(caminho)


def test_arquivo_ausente_falha_citando_o_caminho(tmp_path):
    ausente = tmp_path / "nao-existe.csv"
    with pytest.raises(SamlLoaderError, match="nao-existe.csv"):
        read_header(ausente)


# --- Linhas (rótulos e coerência) ---


def test_rotulo_fora_do_mapeamento_falha_citando_o_rotulo(tmp_path, mapeamento):
    desconhecida = (*SUSPEITA[:11], "Trade_Based_Laundering")
    caminho = _csv(tmp_path, (NORMAL, desconhecida), COLUNAS)
    with pytest.raises(SamlLoaderError) as erro:
        list(iter_transactions(caminho, mapeamento))
    mensagem = str(erro.value)
    assert "'Trade_Based_Laundering'" in mensagem
    assert SAML_D_MAPPING_FILE in mensagem
    assert ":3:" in mensagem


def test_flag_incoerente_com_o_rotulo_falha(tmp_path, mapeamento):
    incoerente = (*SUSPEITA[:10], "0", "Structuring")
    caminho = _csv(tmp_path, (incoerente,), COLUNAS)
    with pytest.raises(SamlLoaderError, match="incoerente com o rótulo 'Structuring'"):
        list(iter_transactions(caminho, mapeamento))


def test_flag_fora_de_zero_ou_um_falha(tmp_path, mapeamento):
    invalida = (*NORMAL[:10], "2", "Normal_Cash_Deposits")
    caminho = _csv(tmp_path, (invalida,), COLUNAS)
    with pytest.raises(SamlLoaderError, match="esperado '0' ou '1'"):
        list(iter_transactions(caminho, mapeamento))


def test_linha_com_numero_de_celulas_errado_falha(tmp_path, mapeamento):
    caminho = _csv(tmp_path, (NORMAL[:-1],), COLUNAS)
    with pytest.raises(SamlLoaderError, match="11 células para 12 colunas"):
        list(iter_transactions(caminho, mapeamento))


def test_linhas_validas_saem_por_nome_de_coluna(tmp_path, mapeamento):
    caminho = _csv(tmp_path, (NORMAL, SUSPEITA), COLUNAS)
    linhas = list(iter_transactions(caminho, mapeamento))
    assert [linha["Laundering_type"] for linha in linhas] == ["Normal_Cash_Deposits", "Structuring"]
    assert linhas[1]["Amount"] == "9500.00"
    assert set(linhas[0]) == set(COLUNAS)


def test_relatorio_conta_suspeitas_e_normais(tmp_path, mapeamento):
    caminho = _csv(tmp_path, (NORMAL, SUSPEITA, NORMAL), COLUNAS)
    relatorio = validate_file(caminho, mapeamento)
    assert relatorio.linhas == 3
    assert relatorio.suspeitas == 1
    assert relatorio.normais == 2
    assert relatorio.por_rotulo == {"Normal_Cash_Deposits": 2, "Structuring": 1}


def test_cabecalho_com_as_duas_flags_falha(tmp_path):
    caminho = _csv(tmp_path, (), (*COLUNAS, "Is_Suspicious"))
    with pytest.raises(SamlLoaderError, match="ambíguas"):
        read_header(caminho)


def test_mapeamento_com_inciso_inexistente_na_norma_falha(tmp_path):
    dados = _raw()
    dados["tipologias"]["Structuring"]["incisos"] = ["XVIII"]
    with pytest.raises(ConfigError, match="não existem no art. 1º da CC 4.001/2020"):
        load_saml_d_mapping(_mapping(tmp_path, dados))


def test_mapeamento_aceita_qualquer_inciso_existente_no_artigo(tmp_path):
    """A guarda é o conjunto de incisos do art. 1º, não os quatro que a mapping_version 1 usa hoje."""
    dados = _raw()
    dados["tipologias"]["Structuring"]["incisos"] = ["II", "XVII"]
    mapeamento = load_saml_d_mapping(_mapping(tmp_path, dados))
    assert mapeamento.tipologias["Structuring"].incisos == ["II", "XVII"]
