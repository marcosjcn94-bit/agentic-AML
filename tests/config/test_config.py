"""Configuração versionada (T0.5): RF-03, RF-04, RF-06, RNF-09, RNF-10, ADR-010, ADR-013 e baseline (SPEC.md §12).

Os casos inválidos partem do arquivo versionado, alteram um único ponto e gravam o YAML em `tmp_path`.
"""

from __future__ import annotations

import ast
import copy
import re
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest
import yaml

from aml_guardian.config import (
    CONFIG_DIR,
    ConfigError,
    Situacao,
    load_baseline,
    load_litellm,
    load_triage_rules,
)

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "aml_guardian"
APPROVED_ON = date(2026, 9, 15)

PROVIDER_OR_MODEL = re.compile(
    r"(?i)(ollama|qwen|llama|openai|anthropic|claude|sonnet|opus|haiku|gpt|gemini|gemma|bedrock|titan|vertex|azure"
    r"|mistral|cohere|command-r|groq|grok|deepseek)"
)
LOCAL_PROVIDERS = {"ollama", "ollama_chat"}


def _raw(name: str) -> dict[str, Any]:
    return copy.deepcopy(yaml.safe_load((CONFIG_DIR / name).read_text(encoding="utf-8")))


def _write(tmp_path: Path, name: str, data: Any) -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def _set(data: dict[str, Any], keys: tuple[str | int, ...], value: Any) -> None:
    node: Any = data
    for key in keys[:-1]:
        node = node[key]
    node[keys[-1]] = value


def test_config_dir_e_o_diretorio_versionado() -> None:
    assert CONFIG_DIR == ROOT / "config"


# --- triage_rules.yaml (RF-03) ---------------------------------------------------------------------------------


def test_config_triage_rules_versionado_carrega_valores_aprovados() -> None:
    rules = load_triage_rules()
    det = rules.detectores_criticos
    assert rules.rules_version == 1
    assert (det.fragmentacao.limiar_brl, det.fragmentacao.min_transacoes, det.fragmentacao.janela_dias) == (
        Decimal("10000.00"),
        3,
        7,
    )
    assert (det.camadas.profundidade_minima, det.camadas.min_contrapartes, det.camadas.janela_dias) == (2, 3, 30)
    assert det.especie_depois_exterior.janela_dias == 7
    assert det.lista_restricao.listas == ["pep", "ceis", "cnep"]
    assert all(d.critico for d in (det.fragmentacao, det.camadas, det.especie_depois_exterior, det.lista_restricao))
    assert (rules.aprovacao.em, rules.aprovacao.situacao) == (APPROVED_ON, Situacao.PROVISORIO)


def test_config_triage_sem_rules_version_falha(tmp_path: Path) -> None:
    data = _raw("triage_rules.yaml")
    del data["rules_version"]
    with pytest.raises(ConfigError, match="rules_version"):
        load_triage_rules(_write(tmp_path, "triage_rules.yaml", data))


@pytest.mark.parametrize(
    ("keys", "value"),
    [
        (("rules_version",), "1"),
        (("rules_version",), 0),
        (("detectores_criticos", "fragmentacao", "min_transacoes"), "3"),
        (("detectores_criticos", "fragmentacao", "min_transacoes"), 3.0),
        (("detectores_criticos", "fragmentacao", "limiar_brl"), 10000.5),
        (("detectores_criticos", "fragmentacao", "limiar_brl"), "10000.001"),
        (("detectores_criticos", "fragmentacao", "critico"), False),
        (("detectores_criticos", "fragmentacao", "critico"), 1),
        (("detectores_criticos", "camadas", "critico"), 1.0),
        (("detectores_criticos", "lista_restricao", "critico"), "true"),
        (("detectores_criticos", "camadas", "profundidade_minima"), 1),
        (("detectores_criticos", "camadas", "janela_dias"), True),
        (("detectores_criticos", "especie_depois_exterior", "janela_dias"), 0),
        (("detectores_criticos", "lista_restricao", "listas"), ["pep", "ofac"]),
        (("detectores_criticos", "lista_restricao", "listas"), ["pep", "pep"]),
        (("detectores_criticos", "lista_restricao", "listas"), []),
        (("aprovacao", "em"), "ontem"),
        (("aprovacao", "em"), "2026-09-15"),
    ],
)
def test_config_triage_parametro_de_tipo_errado_falha(tmp_path: Path, keys: tuple[str, ...], value: Any) -> None:
    data = _raw("triage_rules.yaml")
    _set(data, keys, value)
    with pytest.raises(ConfigError, match=str(keys[-1])):
        load_triage_rules(_write(tmp_path, "triage_rules.yaml", data))


@pytest.mark.parametrize("detector", ["fragmentacao", "camadas", "especie_depois_exterior", "lista_restricao"])
def test_config_triage_detector_critico_ausente_falha(tmp_path: Path, detector: str) -> None:
    data = _raw("triage_rules.yaml")
    del data["detectores_criticos"][detector]
    with pytest.raises(ConfigError, match=detector):
        load_triage_rules(_write(tmp_path, "triage_rules.yaml", data))


def test_config_triage_chave_desconhecida_falha(tmp_path: Path) -> None:
    data = _raw("triage_rules.yaml")
    data["detectores_criticos"]["fragmentacao"]["limiar_extra"] = 1
    with pytest.raises(ConfigError, match="limiar_extra"):
        load_triage_rules(_write(tmp_path, "triage_rules.yaml", data))


@pytest.mark.parametrize(
    ("content", "message"),
    [("", "mapeamento"), ("- rules_version\n", "mapeamento"), ("rules_version: [1\n", "YAML inválido")],
)
def test_config_documento_malformado_falha(tmp_path: Path, content: str, message: str) -> None:
    path = tmp_path / "triage_rules.yaml"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ConfigError, match=message):
        load_triage_rules(path)


def test_config_arquivo_ausente_falha(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="não foi possível ler"):
        load_triage_rules(tmp_path / "nao_existe.yaml")


# --- litellm.yaml (RF-04, RF-06, RNF-09, RNF-10, ADR-010, ADR-013) ---------------------------------------------


def test_config_litellm_versionado_carrega_valores_aprovados() -> None:
    cfg = load_litellm()
    params = cfg.params_for(cfg.investigation.model_alias)
    assert params.model.split("/", 1)[1] == "qwen2.5:1.5b"
    assert (params.temperature, params.seed, params.num_ctx, params.num_predict, params.num_thread) == (
        0,
        42,
        2048,
        60,
        8,
    )
    assert (cfg.cache.enabled, cfg.cache.threshold) == (True, 0.92)
    assert cfg.selection.min_score == 0.35  # ADR-016: alinhado a config/retrieval.yaml (fonte real do código)
    assert cfg.selection.aprovacao.situacao is Situacao.DEFINITIVO
    assert cfg.investigation.aprovacao.situacao is Situacao.DEFINITIVO
    assert len(cfg.model_list) == 2  # ADR-017 (RNF-10): segundo provedor local, mesmo custo zero


@pytest.mark.parametrize(
    ("keys", "value"),
    [
        (("model_list", 0, "litellm_params", "num_ctx"), "2048"),
        (("model_list", 0, "litellm_params", "seed"), 42.0),
        (("model_list", 0, "litellm_params", "temperature"), 0.2),
        (("model_list", 0, "litellm_params", "num_predict"), 61),
        (("model_list", 0, "litellm_params", "num_thread"), 0),
        (("model_list", 0, "litellm_params", "model"), "qwen2.5:1.5b"),
        (("model_list", 0, "litellm_params", "api_base"), "localhost"),
        (("cache", "threshold"), "0,92"),
        (("cache", "threshold"), 0),
        (("cache", "enabled"), "sim"),
        (("selection", "min_score"), 1.5),
        (("selection", "min_score"), None),
    ],
)
def test_config_litellm_parametro_de_tipo_errado_falha(tmp_path: Path, keys: tuple[str | int, ...], value: Any) -> None:
    data = _raw("litellm.yaml")
    _set(data, keys, value)
    with pytest.raises(ConfigError, match=str(keys[-1])):
        load_litellm(_write(tmp_path, "litellm.yaml", data))


@pytest.mark.parametrize("section", ["cache", "selection", "investigation", "model_list"])
def test_config_litellm_secao_ausente_falha(tmp_path: Path, section: str) -> None:
    data = _raw("litellm.yaml")
    del data[section]
    with pytest.raises(ConfigError, match=section):
        load_litellm(_write(tmp_path, "litellm.yaml", data))


def test_config_litellm_alias_ausente_de_model_list_falha(tmp_path: Path) -> None:
    data = _raw("litellm.yaml")
    data["investigation"]["model_alias"] = "outro_alias"
    with pytest.raises(ConfigError, match="outro_alias"):
        load_litellm(_write(tmp_path, "litellm.yaml", data))


def test_config_litellm_model_name_repetido_falha(tmp_path: Path) -> None:
    data = _raw("litellm.yaml")
    data["model_list"].append(copy.deepcopy(data["model_list"][0]))
    with pytest.raises(ConfigError, match="repetido"):
        load_litellm(_write(tmp_path, "litellm.yaml", data))


def test_config_litellm_alias_inexistente_levanta_key_error() -> None:
    with pytest.raises(KeyError):
        load_litellm().params_for("outro_alias")


def test_config_litellm_poc_resolve_apenas_provedor_local() -> None:
    cfg = load_litellm()
    for entry in cfg.model_list:
        assert entry.litellm_params.model.split("/", 1)[0] in LOCAL_PROVIDERS
        assert urlsplit(str(entry.litellm_params.api_base)).hostname in {"localhost", "127.0.0.1"}


def _docstring_nodes(tree: ast.AST) -> set[int]:
    # Decisão consciente: docstring documenta a arquitetura (pode citar o runtime local) e não é valor usado em
    # chamada; a regra do ADR-010/RNF-10 é sobre literal que o código usa para escolher provedor ou modelo.
    owners = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    return {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, owners)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }


def test_config_nome_de_provedor_ou_modelo_nao_aparece_em_codigo() -> None:
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        docstrings = _docstring_nodes(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstrings
                and PROVIDER_OR_MODEL.search(node.value)
            ):
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}: {node.value!r}")
    assert offenders == []


# --- baseline.yaml (SPEC.md §3.3, §10, §12) ----------------------------------------------------------------------


def test_config_baseline_versionado_carrega_premissas_aprovadas() -> None:
    baseline = load_baseline()
    assert (baseline.tempo_manual_min, baseline.tempo_revisao_min) == (120, 15)
    assert (baseline.aprovacao.em, baseline.aprovacao.situacao) == (APPROVED_ON, Situacao.PROVISORIO)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda d: d.update(tempo_manual_min="120"), "tempo_manual_min"),
        (lambda d: d.update(tempo_revisao_min=0), "tempo_revisao_min"),
        (lambda d: d.update(tempo_revisao_min=120), "menor que tempo_manual_min"),
        (lambda d: d.pop("tempo_revisao_min"), "tempo_revisao_min"),
        (lambda d: d.pop("aprovacao"), "aprovacao"),
    ],
)
def test_config_baseline_invalido_falha(
    tmp_path: Path, mutate: Callable[[dict[str, Any]], object], message: str
) -> None:
    data = _raw("baseline.yaml")
    mutate(data)
    with pytest.raises(ConfigError, match=message):
        load_baseline(_write(tmp_path, "baseline.yaml", data))
