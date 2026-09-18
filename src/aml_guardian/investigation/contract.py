"""Contrato congelado da Investigação v1 (T1.6, ADR-010, ADR-013, `prompt_version = 1`).

Instruções, bloco do alerta, schema de geração e expansão reproduzem `scripts/bench_ollama.py` linha a linha
(58-62 instruções; 152-156 bloco do alerta, sem o nonce do benchmark; 164-177 schema; 56 e 190-191 expansão)
— o script não é alterado, só sua forma é seguida (AGENTS.md §4). Mudar qualquer valor aqui é decisão
estrutural: Ask First (AGENTS.md §4.1, §7; SOUL.md §4).
"""

from __future__ import annotations

import json

from pydantic import ValidationError

from aml_guardian.contracts.ingestion import SanitizedAlert
from aml_guardian.contracts.pipeline import MAX_EVIDENCE, Feature, InvestigationOutput, Recommendation, Typology

PROMPT_VERSION = "1"

# Instruções fixas (bench_ollama.py:58-62); sem acentos, texto idêntico ao medido no benchmark.
INVESTIGATION_INSTRUCTIONS = (
    "No de Investigacao PLD/FT. Dados sanitizados: pessoas e contas so como tokens sinteticos.\n"
    "Responda JSON: t=tipologia mais provavel ou NENHUMA; c=confianca 0-1; r=recomendacao; "
    f"e=ate {MAX_EVIDENCE} numeros de feature que sustentam t (F03 -> 3).\n"
)

# Chaves curtas de geração -> campos do DT-07 (bench_ollama.py:56).
OUTPUT_KEYS = {"t": "typology_hypothesis", "c": "confidence", "r": "recommendation", "e": "evidence_feature_ids"}

SUSPICIOUS_TYPOLOGIES = [t.value for t in Typology if t is not Typology.NENHUMA]
RECOMMENDATIONS = [r.value for r in Recommendation]


def schema_geracao(feature_ids_presentes: list[str]) -> dict[str, object]:
    """Schema de geração imposto na chamada ao modelo (bench_ollama.py:164-177)."""
    return {
        "type": "object",
        "properties": {
            "t": {"type": "string", "enum": SUSPICIOUS_TYPOLOGIES + ["NENHUMA"]},
            "c": {"type": "number", "minimum": 0, "maximum": 1},
            "r": {"type": "string", "enum": RECOMMENDATIONS},
            "e": {
                "type": "array",
                "items": {"type": "integer", "enum": [int(f[1:]) for f in feature_ids_presentes]},
                "maxItems": MAX_EVIDENCE,
            },
        },
        "required": list(OUTPUT_KEYS),
    }


def _linha_indicador(feature: Feature) -> str:
    """Uma linha do bloco de indicadores: `F01 nome=valor` (F01-F13) ou `F14 TOKEN in=.. out=.. brl=..` (F14+)."""
    if int(feature.feature_id[1:]) < 14:
        return f"{feature.feature_id} {feature.name}={feature.value}"
    return f"{feature.feature_id} {feature.name} {feature.value}"


def bloco_alerta(sanitized_alert: SanitizedAlert, detectores_disparados: list[str], features: list[Feature]) -> str:
    """Bloco do alerta (bench_ollama.py:152-156), sem nonce — prefixo estável de produção (AGENTS.md §4.1)."""
    alert_ref = str(sanitized_alert.alert_id)[:8]
    token_titular = sanitized_alert.sender_customer.cpf_cnpj
    token_conta = sanitized_alert.sender_account
    disparo = ", ".join(sorted(regra.lower() for regra in detectores_disparados)) or "nenhum detector"
    linhas = "\n".join(_linha_indicador(f) for f in features)
    return (
        f"Alerta {alert_ref} regra {sanitized_alert.source_rule_id} titular {token_titular} conta {token_conta}\n"
        f"Triagem: {disparo} disparou.\nIndicadores:\n{linhas}"
    )


def expandir_saida(raw: dict[str, object]) -> dict[str, object]:
    """Expande as chaves curtas do modelo para os campos do DT-07 (bench_ollama.py:56, 190-191)."""
    expandido: dict[str, object] = {OUTPUT_KEYS[chave]: valor for chave, valor in raw.items()}
    expandido["evidence_feature_ids"] = [f"F{n:02d}" for n in raw["e"]]
    return expandido


def validar_saida(texto: str) -> InvestigationOutput | None:
    """Valida a forma/tipos da resposta (bench_ollama.py:180-200), sem checar existência das evidências.

    A existência de cada `feature_id` no DT-16 é responsabilidade do pós-processamento RF-05 (`descartar
    feature_id inexistente e registrar o descarte`, SPEC.md RF-05), não desta validação de schema — por isso
    esta função não rejeita evidência fora do conjunto presente no prompt, ao contrário do `validate_output`
    do benchmark (decisão registrada no relatório do T1.6, AGENTS.md §4.2 não define o passo de descarte).
    """
    try:
        raw = json.loads(texto)
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, dict) or set(raw) != set(OUTPUT_KEYS) or not isinstance(raw.get("e"), list):
        return None
    if not all(isinstance(n, int) and not isinstance(n, bool) for n in raw["e"]):
        return None
    try:
        return InvestigationOutput.model_validate(expandir_saida(raw))
    except (ValidationError, KeyError, ValueError):
        return None


__all__ = [
    "INVESTIGATION_INSTRUCTIONS",
    "OUTPUT_KEYS",
    "PROMPT_VERSION",
    "RECOMMENDATIONS",
    "SUSPICIOUS_TYPOLOGIES",
    "bloco_alerta",
    "expandir_saida",
    "schema_geracao",
    "validar_saida",
]
