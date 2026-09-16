"""Calendário versionado `config/feriados.yaml` (T0.5, RF-09): completude, fontes oficiais e validação do loader.

O esperado é recalculado no teste a partir das regras (datas fixas de lei federal e datas móveis pela Páscoa),
de forma independente das datas listadas no arquivo.
"""

from __future__ import annotations

import copy
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest
import yaml

from aml_guardian.config import CONFIG_DIR, ConfigError, Situacao, load_feriados

FIXED_FEDERAL = [(1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2), (11, 15), (12, 25)]
CONSCIENCIA_NEGRA_DESDE = 2024
OFFICIAL_HOSTS = ("planalto.gov.br", "bcb.gov.br")


def _easter(year: int) -> date:
    """Domingo de Páscoa pelo algoritmo gregoriano anônimo (Meeus/Jones/Butcher)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    lval = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * lval) // 451
    month = (h + lval - 7 * m + 114) // 31
    day = (h + lval - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def _expected(year: int) -> set[date]:
    dates = {date(year, month, day) for month, day in FIXED_FEDERAL}
    if year >= CONSCIENCIA_NEGRA_DESDE:
        dates.add(date(year, 11, 20))
    easter = _easter(year)
    # Res. CMN 4.880/2020, art. 6º: segunda e terça de Carnaval e Corpus Christi; Sexta-feira da Paixão fica fora.
    dates.update({easter - timedelta(days=48), easter - timedelta(days=47), easter + timedelta(days=60)})
    return dates


def _raw() -> dict[str, Any]:
    return copy.deepcopy(yaml.safe_load((CONFIG_DIR / "feriados.yaml").read_text(encoding="utf-8")))


def _load(tmp_path: Path, data: dict[str, Any]):
    path = tmp_path / "feriados.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return load_feriados(path)


def test_config_easter_de_referencia() -> None:
    assert [_easter(y) for y in (2022, 2023, 2026)] == [date(2022, 4, 17), date(2023, 4, 9), date(2026, 4, 5)]


def test_config_feriados_versionado_cobre_2022_a_2027_sem_data_extra() -> None:
    cfg = load_feriados()
    assert (cfg.periodo.ano_inicio, cfg.periodo.ano_fim) == (2022, 2027)
    expected = set().union(*(_expected(y) for y in range(2022, 2028)))
    assert cfg.datas == expected
    assert cfg.aprovacao.situacao is Situacao.DEFINITIVO


def test_config_feriados_fontes_oficiais_com_url_governamental() -> None:
    cfg = load_feriados()
    for fonte in cfg.fontes:
        host = urlsplit(str(fonte.url)).hostname or ""
        assert fonte.url.scheme == "https"
        assert host.endswith(OFFICIAL_HOSTS), fonte.id
    assert {f.fonte for f in cfg.feriados} == {fonte.id for fonte in cfg.fontes}


@pytest.mark.parametrize(
    ("dia", "esperado"),
    [
        (date(2026, 2, 17), True),  # terça de Carnaval
        (date(2026, 2, 18), False),  # quarta-feira de Cinzas
        (date(2026, 4, 3), False),  # Sexta-feira da Paixão: fora da Res. CMN 4.880/2020
        (date(2026, 6, 4), True),  # Corpus Christi
        (date(2023, 11, 20), False),  # antes da Lei 14.759/2023
        (date(2024, 11, 20), True),
        (date(2027, 12, 25), True),
    ],
)
def test_config_feriados_is_feriado(dia: date, esperado: bool) -> None:
    assert load_feriados().is_feriado(dia) is esperado


@pytest.mark.parametrize("dia", [date(2021, 12, 31), date(2028, 1, 3)])
def test_config_feriados_consulta_fora_do_periodo_falha(dia: date) -> None:
    with pytest.raises(ValueError, match="fora do período"):
        load_feriados().is_feriado(dia)


def test_config_feriados_data_fora_do_periodo_falha(tmp_path: Path) -> None:
    data = _raw()
    data["feriados"].append({"data": date(2028, 1, 1), "nome": "Confraternização", "fonte": data["fontes"][0]["id"]})
    with pytest.raises(ConfigError, match="fora do período"):
        _load(tmp_path, data)


def test_config_feriados_fonte_nao_declarada_falha(tmp_path: Path) -> None:
    data = _raw()
    data["feriados"][0]["fonte"] = "fonte_inexistente"
    with pytest.raises(ConfigError, match="fonte_inexistente"):
        _load(tmp_path, data)


def test_config_feriados_data_repetida_falha(tmp_path: Path) -> None:
    data = _raw()
    data["feriados"].insert(1, copy.deepcopy(data["feriados"][0]))
    with pytest.raises(ConfigError, match="ordem crescente"):
        _load(tmp_path, data)


def test_config_feriados_fora_de_ordem_falha(tmp_path: Path) -> None:
    data = _raw()
    data["feriados"][0], data["feriados"][1] = data["feriados"][1], data["feriados"][0]
    with pytest.raises(ConfigError, match="ordem crescente"):
        _load(tmp_path, data)


@pytest.mark.parametrize(
    ("keys", "value", "message"),
    [
        (("feriados", 0, "data"), "2022-01-01", "data"),
        (("periodo", "ano_inicio"), "2022", "ano_inicio"),
        (("periodo", "ano_inicio"), 2030, "ano_inicio posterior"),
        (("fontes", 0, "url"), "sem-url", "url"),
    ],
)
def test_config_feriados_tipo_errado_falha(
    tmp_path: Path, keys: tuple[str | int, ...], value: Any, message: str
) -> None:
    data = _raw()
    node: Any = data
    for key in keys[:-1]:
        node = node[key]
    node[keys[-1]] = value
    with pytest.raises(ConfigError, match=message):
        _load(tmp_path, data)


def test_config_feriados_id_de_fonte_repetido_falha(tmp_path: Path) -> None:
    data = _raw()
    data["fontes"].append(copy.deepcopy(data["fontes"][0]))
    with pytest.raises(ConfigError, match="fonte repetido"):
        _load(tmp_path, data)
