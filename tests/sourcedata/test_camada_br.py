"""Câmbio sintético e mapeamento SAML-D → DT-02 da camada brasileira (T0.7): SPEC.md §8.3, decisões do Ask First.

Os casos inválidos partem do arquivo versionado, alteram um único ponto e gravam em `tmp_path`.
O conteúdo do `core_sintetico.sqlite` fica em `test_camada_br_core.py`; as fixtures, em `conftest.py`.
"""

from __future__ import annotations

import copy
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml

from aml_guardian.config import CONFIG_DIR, ConfigError
from aml_guardian.config.cambio import CAMBIO_FILE, CambioError, load_cambio
from aml_guardian.contracts.ingestion import PaymentType
from aml_guardian.sourcedata import MAPPINGS_DIR
from aml_guardian.sourcedata.br_mapping import (
    PAISES_SAML_D,
    PAYMENT_TYPES_SAML_D,
    SAML_D_BR_FILE,
    BrMappingError,
    load_br_mapping,
)


def _raw(diretorio: Path, arquivo: str) -> dict[str, Any]:
    return copy.deepcopy(yaml.safe_load((diretorio / arquivo).read_text(encoding="utf-8")))


def _grava(tmp_path: Path, nome: str, dados: dict[str, Any]) -> Path:
    destino = tmp_path / nome
    destino.write_text(yaml.safe_dump(dados, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return destino


# --- Câmbio sintético versionado (T0.7 Ask First) ---


def test_cambio_versionado_carrega(cambio):
    assert cambio.cambio_version == 1
    assert len(cambio.moedas) == 13
    assert cambio.iso("UK pounds") == "GBP"
    assert cambio.iso("Moroccan dirham") == "MAD"


def test_cambio_cobre_todas_as_moedas_do_saml_d(cambio):
    esperado = {
        "Dirham",
        "Moroccan dirham",
        "Naira",
        "Albanian lek",
        "UK pounds",
        "Mexican Peso",
        "Yen",
        "Swiss franc",
        "Turkish lira",
        "Euro",
        "US dollar",
        "Indian rupee",
        "Pakistani rupee",
    }
    assert set(cambio.moedas) == esperado


def test_conversao_arredonda_para_duas_casas(cambio):
    assert cambio.converte("1459.15", "UK pounds") == Decimal("9046.73")
    assert cambio.converte("100.00", "US dollar") == Decimal("500.00")


def test_conversao_do_menor_valor_da_menor_taxa_continua_positiva(cambio):
    """O menor Amount em Naira do SAML-D real (13,91) não pode arredondar para zero (DT-02 exige > 0)."""
    assert cambio.converte("13.91", "Naira") == Decimal("0.09")


def test_conversao_recusa_moeda_fora_da_tabela(cambio):
    with pytest.raises(CambioError, match="Bitcoin"):
        cambio.converte("10.00", "Bitcoin")


def test_conversao_que_zeraria_o_valor_falha(cambio):
    with pytest.raises(CambioError, match="0"):
        cambio.converte("0.001", "Naira")


def test_conversao_recusa_float(cambio):
    """`float` não entra na aritmética monetária: o DT-02 exige decimal exato."""
    with pytest.raises(CambioError, match="float"):
        cambio.converte(10.5, "Euro")


def test_conversao_recusa_valor_nao_numerico(cambio):
    with pytest.raises(CambioError, match="numérico"):
        cambio.converte("dez", "Euro")


def test_cambio_com_taxa_float_falha(tmp_path):
    dados = _raw(CONFIG_DIR, CAMBIO_FILE)
    dados["moedas"]["Euro"]["taxa_brl"] = 5.4
    with pytest.raises(ConfigError, match="taxa_brl"):
        load_cambio(_grava(tmp_path, CAMBIO_FILE, dados))


def test_cambio_com_taxa_zero_falha(tmp_path):
    dados = _raw(CONFIG_DIR, CAMBIO_FILE)
    dados["moedas"]["Euro"]["taxa_brl"] = "0"
    with pytest.raises(ConfigError, match="taxa_brl"):
        load_cambio(_grava(tmp_path, CAMBIO_FILE, dados))


def test_cambio_com_iso_invalido_falha(tmp_path):
    dados = _raw(CONFIG_DIR, CAMBIO_FILE)
    dados["moedas"]["Euro"]["iso"] = "euro"
    with pytest.raises(ConfigError, match="iso"):
        load_cambio(_grava(tmp_path, CAMBIO_FILE, dados))


def test_cambio_com_iso_repetido_falha(tmp_path):
    dados = _raw(CONFIG_DIR, CAMBIO_FILE)
    dados["moedas"]["Euro"]["iso"] = "GBP"
    with pytest.raises(ConfigError, match="GBP"):
        load_cambio(_grava(tmp_path, CAMBIO_FILE, dados))


# --- Mapeamento SAML-D → DT-02 (T0.7 Ask First) ---


def test_todo_payment_type_do_saml_d_esta_mapeado(br):
    assert set(br.payment_types) == PAYMENT_TYPES_SAML_D
    assert len(PAYMENT_TYPES_SAML_D) == 7


def test_mapeamento_cobre_todo_o_enum_payment_type(br):
    assert set(br.payment_types.values()) == set(PaymentType)


def test_decisoes_do_ask_first_da_t07(br):
    assert br.payment_type("ACH") is PaymentType.PIX
    assert br.payment_type("Cheque") is PaymentType.TED
    assert br.payment_type("Cash Deposit") is PaymentType.ESPECIE_DEPOSITO
    assert br.payment_type("Debit card") is br.payment_type("Credit card") is PaymentType.CARTAO


def test_todo_pais_do_saml_d_esta_mapeado(br):
    assert set(br.paises) == PAISES_SAML_D
    assert len(PAISES_SAML_D) == 18


def test_reino_unido_e_o_unico_pais_domestico(br):
    assert br.pais("UK") == "BR"
    assert br.pais_domestico == "UK"
    assert [rotulo for rotulo, sigla in br.paises.items() if sigla == "BR"] == ["UK"]


def test_mapeamento_recusa_payment_type_desconhecido(br):
    with pytest.raises(BrMappingError, match="Pix Saque"):
        br.payment_type("Pix Saque")


def test_mapeamento_recusa_pais_desconhecido(br):
    with pytest.raises(BrMappingError, match="Narnia"):
        br.pais("Narnia")


def test_mapeamento_sem_um_payment_type_falha(tmp_path):
    dados = _raw(MAPPINGS_DIR, SAML_D_BR_FILE)
    del dados["payment_types"]["Cheque"]
    with pytest.raises(ConfigError, match="Cheque"):
        load_br_mapping(_grava(tmp_path, SAML_D_BR_FILE, dados))


def test_mapeamento_com_dois_paises_domesticos_falha(tmp_path):
    dados = _raw(MAPPINGS_DIR, SAML_D_BR_FILE)
    dados["paises"]["Germany"] = "BR"
    with pytest.raises(ConfigError, match="BR"):
        load_br_mapping(_grava(tmp_path, SAML_D_BR_FILE, dados))


def test_mapeamento_sem_pais_domestico_falha(tmp_path):
    dados = _raw(MAPPINGS_DIR, SAML_D_BR_FILE)
    dados["paises"]["UK"] = "GB"
    with pytest.raises(ConfigError, match="BR"):
        load_br_mapping(_grava(tmp_path, SAML_D_BR_FILE, dados))


def test_mapeamento_com_pais_fora_do_saml_d_falha(tmp_path):
    dados = _raw(MAPPINGS_DIR, SAML_D_BR_FILE)
    dados["paises"]["Narnia"] = "NA"
    with pytest.raises(ConfigError, match="Narnia"):
        load_br_mapping(_grava(tmp_path, SAML_D_BR_FILE, dados))
