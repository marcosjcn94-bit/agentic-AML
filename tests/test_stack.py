"""Guarda da stack (SPEC.md §6 — obrigatória e proibida; T0.1).

Falha se o `pyproject.toml` declarar, ou se algum módulo em `src/` importar,
SDK proprietário de nuvem ou de provedor de modelo. Dependências transitivas
(ex.: `openai` trazido pelo `litellm`) ficam fora do escopo: a regra é não
declarar nem importar diretamente.
"""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
SRC = ROOT / "src"

FORBIDDEN_DISTRIBUTIONS = {"openai", "anthropic", "boto3", "azure", "google-cloud"}
FORBIDDEN_DISTRIBUTION_PREFIXES = ("google-cloud-", "azure-")
FORBIDDEN_IMPORT_ROOTS = {"openai", "anthropic", "boto3", "azure"}
FORBIDDEN_IMPORT_PREFIXES = ("google.cloud",)

_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def _normalize(name: str) -> str:
    """Nome canônico PEP 503 (minúsculo, separadores unificados em `-`)."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _requirement_name(requirement: str) -> str:
    match = _NAME_RE.match(requirement)
    if match is None:
        raise ValueError(f"requisito sem nome de distribuição: {requirement!r}")
    return _normalize(match.group(1))


def _is_forbidden_distribution(requirement: str) -> bool:
    name = _requirement_name(requirement)
    return name in FORBIDDEN_DISTRIBUTIONS or name.startswith(FORBIDDEN_DISTRIBUTION_PREFIXES)


def _is_forbidden_module(module: str) -> bool:
    root = module.split(".", 1)[0]
    return root in FORBIDDEN_IMPORT_ROOTS or any(
        module == prefix or module.startswith(prefix + ".") for prefix in FORBIDDEN_IMPORT_PREFIXES
    )


def _imported_modules(source: str) -> list[str]:
    """Módulos importados estática ou dinamicamente (literal em `import_module`/`__import__`)."""
    modules: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.append(node.module)
            modules.extend(f"{node.module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Call):
            func = node.func
            func_name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if func_name not in {"import_module", "__import__"}:
                continue
            candidates = node.args[:1] + [kw.value for kw in node.keywords if kw.arg == "name"]
            modules.extend(
                arg.value for arg in candidates if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
            )
    return modules


def _declared_requirements(pyproject: dict) -> list[str]:
    project = pyproject.get("project", {})
    requirements = list(pyproject.get("build-system", {}).get("requires", []))
    requirements.extend(project.get("dependencies", []))
    for extra in project.get("optional-dependencies", {}).values():
        requirements.extend(extra)
    for group in pyproject.get("dependency-groups", {}).values():
        requirements.extend(item for item in group if isinstance(item, str))
    return requirements


@pytest.mark.parametrize(
    ("requirement", "forbidden"),
    [
        ("openai>=1.0", True),
        ("Anthropic", True),
        ("boto3==1.35", True),
        ("google-cloud-storage", True),
        ("google_cloud_aiplatform>=1", True),
        ("azure-identity", True),
        ("azure", True),
        ("google-cloud", True),
        ("litellm>=1.50", False),
        ("google-auth", False),
        ("pt_core_news_lg @ https://example.invalid/pt_core_news_lg-3.8.0-py3-none-any.whl", False),
    ],
)
def test_stack_classificador_de_distribuicoes(requirement: str, forbidden: bool) -> None:
    assert _is_forbidden_distribution(requirement) is forbidden


@pytest.mark.parametrize(
    ("source", "forbidden"),
    [
        ("import openai", True),
        ("from anthropic import Anthropic", True),
        ("import boto3.session", True),
        ("from google.cloud import storage", True),
        ("from google import cloud", True),
        ("import azure.identity", True),
        ("import importlib\nimportlib.import_module('openai')", True),
        ("__import__('anthropic')", True),
        ("import importlib\nimportlib.import_module(name='boto3')", True),
        ("import litellm", False),
        ("from google.protobuf import message", False),
        ("from . import openai", False),
    ],
)
def test_stack_classificador_de_imports(source: str, forbidden: bool) -> None:
    assert any(_is_forbidden_module(m) for m in _imported_modules(source)) is forbidden


def test_stack_python_minimo() -> None:
    assert sys.version_info >= (3, 11)
    requires = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["requires-python"]
    assert requires.replace(" ", "") == ">=3.11"


def test_stack_pyproject_sem_dependencia_proibida() -> None:
    pyproject = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    requirements = _declared_requirements(pyproject)
    assert requirements, "pyproject.toml sem dependências declaradas"
    assert [r for r in requirements if _is_forbidden_distribution(r)] == []


def test_stack_declaracoes_incluem_build_system() -> None:
    pyproject = {"build-system": {"requires": ["setuptools>=69", "boto3"]}, "project": {"dependencies": []}}
    assert "boto3" in _declared_requirements(pyproject)


def test_stack_src_sem_import_proibido() -> None:
    files = sorted(SRC.rglob("*.py"))
    assert files, "src/ sem módulos Python"
    offenders = [
        f"{path.relative_to(ROOT)}: {module}"
        for path in files
        for module in _imported_modules(path.read_text(encoding="utf-8"))
        if _is_forbidden_module(module)
    ]
    assert offenders == []
