from __future__ import annotations

import pytest

from aml_guardian.sourcedata.golden import GoldenSetError, _distribui_agua


def test_distribui_agua_divide_igualmente_quando_ha_sobra_para_todos():
    resultado = _distribui_agua({"A": 50, "B": 50, "C": 50}, total=30)
    assert resultado == {"A": 10, "B": 10, "C": 10}


def test_distribui_agua_trava_rotulo_escasso_e_redistribui_o_resto():
    resultado = _distribui_agua({"A": 2, "B": 50, "C": 50}, total=30)
    assert resultado == {"A": 2, "B": 14, "C": 14}


def test_distribui_agua_sobra_indivisivel_vai_para_os_primeiros_em_ordem_alfabetica():
    resultado = _distribui_agua({"A": 50, "B": 50, "C": 50}, total=31)
    assert resultado == {"A": 11, "B": 10, "C": 10}


def test_distribui_agua_encadeia_travas_em_mais_de_uma_rodada():
    resultado = _distribui_agua({"A": 1, "B": 2, "C": 50, "D": 50}, total=30)
    assert resultado == {"A": 1, "B": 2, "C": 14, "D": 13}


def test_distribui_agua_levanta_erro_se_total_pedido_excede_disponibilidade():
    with pytest.raises(GoldenSetError, match="disponib"):
        _distribui_agua({"A": 1, "B": 1}, total=10)
