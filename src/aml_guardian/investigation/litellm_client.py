"""Cliente LiteLLM da Investigação (T1.6, ADR-010, RNF-10): roteia pelo alias de `config/litellm.yaml`.

O modelo é sempre resolvido pelo alias `investigation.model_alias` — nunca hardcoded aqui (RNF-10, sem
lock-in). O contador é um callback síncrono: soma chamadas e tokens a partir de `ModelResponse.usage` e nunca
grava o texto do prompt nem da resposta (RF-11). Ele roda diretamente após a chamada, e não pelo registro
assíncrono `litellm.success_callback`, para não depender de temporização não determinística em teste.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import litellm

from aml_guardian.config.litellm import LiteLLMConfig, LiteLLMParams, load_litellm


@dataclass
class ContadorChamadas:
    """Callback do nó Investigação: conta chamadas e tokens, nunca prompt nem resposta (RF-11)."""

    chamadas: int = 0
    tokens_in: int = 0
    tokens_out: int = 0

    def registrar(self, tokens_in: int, tokens_out: int) -> None:
        self.chamadas += 1
        self.tokens_in += tokens_in
        self.tokens_out += tokens_out


@dataclass(frozen=True)
class RespostaModelo:
    texto: str
    model_id: str
    tokens_in: int
    tokens_out: int
    latency_ms: int


def resolver_params(config: LiteLLMConfig | None = None) -> LiteLLMParams:
    """Parâmetros do alias de investigação (ADR-010, ADR-013): único ponto que conhece provedor e modelo."""
    cfg = config or load_litellm()
    return cfg.params_for(cfg.investigation.model_alias)


def chamar_modelo(
    params: LiteLLMParams,
    prompt: str,
    schema: dict[str, object],
    contador: ContadorChamadas,
    **overrides: object,
) -> RespostaModelo:
    """Chama o modelo via LiteLLM (RNF-10) e devolve texto e métricas; `overrides` só para `mock_response` em teste."""
    inicio = time.perf_counter()
    resposta = litellm.completion(
        model=params.model,
        messages=[{"role": "user", "content": prompt}],
        api_base=str(params.api_base),
        temperature=params.temperature,
        seed=params.seed,
        format=schema,
        num_predict=params.num_predict,
        num_ctx=params.num_ctx,
        num_thread=params.num_thread,
        **overrides,
    )
    latencia_ms = round((time.perf_counter() - inicio) * 1000)
    texto = resposta.choices[0].message.content
    tokens_in = resposta.usage.prompt_tokens if resposta.usage else 0
    tokens_out = resposta.usage.completion_tokens if resposta.usage else 0
    contador.registrar(tokens_in, tokens_out)
    return RespostaModelo(
        texto=texto, model_id=resposta.model, tokens_in=tokens_in, tokens_out=tokens_out, latency_ms=latencia_ms
    )
