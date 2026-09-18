"""Monta e grava `reports/eval-golden-<data>.json`/`.md` (`--golden`, `SPEC.md` §10): agregados do golden set
real, sem dado pessoal (só `alert_id`, estrato/tipologia e métricas numéricas)."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path

from aml_guardian.config.baseline import BaselineConfig, load_baseline
from aml_guardian.eval.gates import percentil
from aml_guardian.eval.golden_gates import avalia_gates_golden
from aml_guardian.eval.golden_runner import AmostraGolden
from aml_guardian.features.catalog import FEATURES_VERSION
from aml_guardian.investigation.contract import PROMPT_VERSION
from aml_guardian.sourcedata.golden_manifest import GoldenManifest


def monta_relatorio_golden(
    manifesto: GoldenManifest,
    amostras: list[AmostraGolden],
    auditoria_valida: bool,
    privacidade_limpo: bool,
    privacidade_ocorrencias: int,
    baseline: BaselineConfig | None = None,
    gerado_em: datetime | None = None,
) -> dict[str, object]:
    baseline = baseline or load_baseline()
    gerado_em = gerado_em or datetime.now(UTC)
    gates = avalia_gates_golden(amostras, baseline, auditoria_valida, privacidade_limpo, privacidade_ocorrencias)
    latencias_ms = [a.total_ms for a in amostras]

    return {
        "gerado_em": gerado_em.isoformat(),
        "golden_version": manifesto.golden_version,
        "manifest_sha256": manifesto.manifest_sha256,
        "amostra": {
            "tamanho": len(amostras),
            "criticos": sum(1 for a in amostras if a.critica),
            "normais": sum(1 for a in amostras if a.normal),
            "nao_criticos_suspeitos": sum(1 for a in amostras if not a.critica and not a.normal),
        },
        "versoes": {
            "rules_version": manifesto.alert_rules_version,
            "mapping_version": manifesto.mapping_version,
            "features_version": FEATURES_VERSION,
            "prompt_version": PROMPT_VERSION,
        },
        "latencia_fluxo_investigar_ms": {
            "p50": percentil(latencias_ms, 50) if latencias_ms else None,
            "p95": percentil(latencias_ms, 95) if latencias_ms else None,
        },
        "baseline": {
            "tempo_manual_min": baseline.tempo_manual_min,
            "tempo_revisao_min": baseline.tempo_revisao_min,
        },
        "gates": [asdict(g) for g in gates],
    }


def _linha_gate(g: dict[str, object]) -> str:
    aprovado = g["aprovado"]
    marca = "—" if aprovado is None else ("✅" if aprovado else "❌")
    valor = g["valor"] if g["valor"] is not None else "-"
    return f"| {g['metrica']} | {g['formula']} | {g['gate']} | {g['status']} | {valor} | {marca} |\n\n  {g['nota']}"


def _markdown(relatorio: dict[str, object]) -> str:
    v = relatorio["versoes"]
    lat = relatorio["latencia_fluxo_investigar_ms"]
    a = relatorio["amostra"]
    linhas = [
        "# Relatório de avaliação — golden set (SPEC.md §10)",
        "",
        f"Gerado em: {relatorio['gerado_em']}",
        f"Golden set: `{relatorio['golden_version']}`, manifest_sha256 `{relatorio['manifest_sha256']}`",
        f"Amostra: {a['tamanho']} alerta(s) ({a['criticos']} tipologia crítica, {a['nao_criticos_suspeitos']} "
        f"tipologia suspeita não crítica, {a['normais']} normal).",
        "",
        "## Versões gravadas",
        "",
        f"- `rules_version`: {v['rules_version']}",
        f"- `mapping_version`: {v['mapping_version']}",
        f"- `features_version`: {v['features_version']}",
        f"- `prompt_version`: {v['prompt_version']}",
        "",
        "## Latência (fluxo `INVESTIGAR`/`PROPOR_ARQUIVAMENTO` completo, golden set real)",
        "",
        f"- p50 = {lat['p50']:.0f} ms, p95 = {lat['p95']:.0f} ms" if lat["p50"] is not None else "- sem amostra",
        "",
        "## Gates Go/No-Go (`SPEC.md` §10)",
        "",
        "| Métrica | Fórmula | Gate | Status | Valor | Aprovado |",
        "| :--- | :--- | :--- | :--- | :--- | :---: |",
        *[_linha_gate(g) for g in relatorio["gates"]],
        "",
        "**Go:** todos os gates atendidos. **No-Go:** recall, grounding final, privacidade ou integridade "
        "falhando — sem exceção (`SPEC.md` §10).",
        "",
    ]
    return "\n".join(linhas)


def escreve_relatorio_golden(
    relatorio: dict[str, object], out_dir: Path, hoje: date | None = None
) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    hoje = hoje or datetime.now(UTC).date()
    base = out_dir / f"eval-golden-{hoje.isoformat()}"
    json_path = base.with_suffix(".json")
    md_path = base.with_suffix(".md")
    json_path.write_text(json.dumps(relatorio, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(_markdown(relatorio), encoding="utf-8")
    return json_path, md_path
