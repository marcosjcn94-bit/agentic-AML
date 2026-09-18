"""Avaliador do projeto (T1.13 + fechamento dos gates do `SPEC.md` §10, `tasks/final-tasks.md` Tarefa A).

Modo padrão: roda uma amostra sintética `INVESTIGAR` ponta a ponta pela API-01, mede a latência do fluxo e
grava `reports/eval-<data>.json`/`.md` (3 gates medidos, 6 "não medida" — T1.13).

Modo `--golden <dir>`: roda o golden set real (`data/golden/v1`, 500 alertas ou os `--limit` primeiros) pelo
pipeline real via API-01 e grava `reports/eval-golden-<data>.json`/`.md` com os 9 gates do `SPEC.md` §10
(`aml_guardian.eval.golden_runner`/`golden_gates`/`golden_report`).

Por padrão usa um modelo simulado (determinístico, sem depender do Ollama estar de pé). `--ollama` chama o
modelo real configurado em `config/litellm.yaml` (ADR-013) — mais lento, mas é o número que fecha os gates.

Uso: python scripts/evaluate.py [--sample-size 3] [--ollama] [--out-dir reports]
     python scripts/evaluate.py --golden data/golden/v1 [--limit 10] [--ollama] [--out-dir reports]
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from aml_guardian.config.triage import load_triage_rules
from aml_guardian.eval.golden_report import escreve_relatorio_golden, monta_relatorio_golden
from aml_guardian.eval.golden_runner import escaneia_privacidade, roda_golden
from aml_guardian.eval.latency import mede_fluxo_investigar
from aml_guardian.eval.report import escreve_relatorio, monta_relatorio
from aml_guardian.sourcedata.mapping import load_saml_d_mapping

_MOCK_RESPONSE = json.dumps({"t": "Structuring", "c": 0.8, "r": "COMUNICAR", "e": [3]})


def _roda_amostra_sintetica(args: argparse.Namespace) -> int:
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


def _roda_golden(args: argparse.Namespace) -> int:
    golden_dir = args.golden
    manifest_path = golden_dir / "manifest.json"
    payloads_dir = golden_dir / "payloads"
    mock_response = None if args.ollama else _MOCK_RESPONSE

    with tempfile.TemporaryDirectory() as tmp:
        manifesto, amostras, auditoria_valida, db_path = roda_golden(
            manifest_path, payloads_dir, Path(tmp), mock_response=mock_response, limit=args.limit
        )
        privacidade_limpo, privacidade_ocorrencias = escaneia_privacidade(
            db_path, payloads_dir, [a.alert_id for a in amostras]
        )

    relatorio = monta_relatorio_golden(
        manifesto, amostras, auditoria_valida, privacidade_limpo, privacidade_ocorrencias
    )
    json_path, md_path = escreve_relatorio_golden(relatorio, args.out_dir)
    print(f"Relatório gravado em {json_path} e {md_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sample-size", type=int, default=3, help="Nº de alertas sintéticos INVESTIGAR (padrão 3)")
    parser.add_argument(
        "--golden",
        type=Path,
        default=None,
        help="Roda o golden set real em vez da amostra sintética (ex.: data/golden/v1)",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Só com --golden: roda só os N primeiros alertas do manifesto"
    )
    parser.add_argument("--ollama", action="store_true", help="Chama o modelo real via LiteLLM em vez do mock")
    parser.add_argument("--out-dir", type=Path, default=Path("reports"), help="Diretório de saída (padrão reports/)")
    args = parser.parse_args(argv)

    if args.golden is not None:
        if args.limit is not None and args.limit < 1:
            parser.error("--limit deve ser >= 1")
        return _roda_golden(args)

    if args.sample_size < 1:
        parser.error("--sample-size deve ser >= 1")
    return _roda_amostra_sintetica(args)


if __name__ == "__main__":
    raise SystemExit(main())
