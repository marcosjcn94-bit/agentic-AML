"""Avaliador inicial do M1 (T1.13, RNF-03 informativa, `SPEC.md` §10, `TASKS.md` T1.13).

Roda uma amostra sintética `INVESTIGAR` ponta a ponta pela API-01 (`aml_guardian.eval`), mede a latência do
fluxo e grava `reports/eval-<data>.json`/`.md` com as versões, o baseline e os 9 gates do `SPEC.md` §10 — os
ainda não implementados aparecem como "não medida", nunca "aprovado" (TASKS.md T1.13).

Por padrão usa um modelo simulado (determinístico, sem depender do Ollama estar de pé). `--ollama` chama o
modelo real configurado em `config/litellm.yaml` (ADR-013) — mais lento, mas é o número que fecha o "Pronto
quando" da tarefa (overhead do grafo sobre os 15,0 s estimados no ADR-013).

Uso: python scripts/evaluate.py [--sample-size 3] [--ollama] [--out-dir reports]
Não recebe `--golden`: a amostra é sintética por construção (TASKS.md T1.13 "Teste focado"); o golden set
completo (data/golden/v1) fica para o avaliador de fim de marco a partir de M3/M7 (TASKS.md §5).
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from aml_guardian.config.triage import load_triage_rules
from aml_guardian.eval.latency import mede_fluxo_investigar
from aml_guardian.eval.report import escreve_relatorio, monta_relatorio
from aml_guardian.sourcedata.mapping import load_saml_d_mapping

_MOCK_RESPONSE = json.dumps({"t": "Structuring", "c": 0.8, "r": "COMUNICAR", "e": [3]})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sample-size", type=int, default=3, help="Nº de alertas sintéticos INVESTIGAR (padrão 3)")
    parser.add_argument("--ollama", action="store_true", help="Chama o modelo real via LiteLLM em vez do mock")
    parser.add_argument("--out-dir", type=Path, default=Path("reports"), help="Diretório de saída (padrão reports/)")
    args = parser.parse_args(argv)
    if args.sample_size < 1:
        parser.error("--sample-size deve ser >= 1")

    mock_response = None if args.ollama else _MOCK_RESPONSE
    with tempfile.TemporaryDirectory() as tmp:
        amostras, auditoria_valida = mede_fluxo_investigar(args.sample_size, Path(tmp), mock_response=mock_response)

    relatorio = monta_relatorio(
        amostras,
        auditoria_valida,
        rules_version=load_triage_rules().rules_version,
        mapping_version=load_saml_d_mapping().mapping_version,
    )
    json_path, md_path = escreve_relatorio(relatorio, args.out_dir)
    print(f"Relatório gravado em {json_path} e {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
