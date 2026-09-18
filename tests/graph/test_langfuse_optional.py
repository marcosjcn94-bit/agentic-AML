"""ADR-018: opt-in por env var, sem env var → grafo roda idêntico, sem overhead."""

from __future__ import annotations


def test_sem_env_var_retorna_lista_vazia(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

    from aml_guardian.graph.build import build_callbacks

    assert build_callbacks() == []


def test_sem_secret_retorna_lista_vazia_mesmo_com_public(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-teste")
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

    from aml_guardian.graph.build import build_callbacks

    assert build_callbacks() == []


def test_com_ambas_retorna_handler(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-teste")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-teste")
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)

    from langfuse.langchain import CallbackHandler

    from aml_guardian.graph.build import build_callbacks

    callbacks = build_callbacks()
    assert len(callbacks) == 1
    assert isinstance(callbacks[0], CallbackHandler)
