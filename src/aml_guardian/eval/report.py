"""Monta e grava `reports/eval-<data>.json`/`.md` (T1.13, `SPEC.md` §10): sem dado pessoal, só agregados.

Amostra sintética gerada em runtime (`eval/fixtures.py`) — nenhum token, CPF/CNPJ ou nome real entra no
relatório; só `alert_id` (UUID sintético) e métricas numéricas.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path

from aml_guardian.config.baseline import BaselineConfig, load_baseline
from aml_guardian.eval.gates import avalia_gates, percentil
from aml_guardian.eval.latency import AmostraLatencia
from aml_guardian.features.catalog import FEATURES_VERSION
from aml_guardian.investigation.contract import PROMPT_VERSION

ADR_013_ESTIMATIVA_S = 15.0  # docs/ADR.md ADR-013: fluxo estimado (Investigação a frio, p95 11,5 s + margem)


def _versoes(amostras: list[AmostraLatencia], rules_version: int, mapping_version: int) -> dict[str, object]:
    modelos = {a.model_id for a in amostras if a.model_id}
    return {
        "rules_version": rules_version,
        "mapping_version": mapping_version,
        "features_version": FEATURES_VERSION,
        "prompt_version": PROMPT_VERSION,
        "model": sorted(modelos)[0] if len(modelos) == 1 else sorted(modelos) or None,
        "corpus_version": "eval-amostra-sintetica",
    }


def monta_relatorio(
    amostras: list[AmostraLatencia],
    auditoria_valida: bool,
    rules_version: int,
    mapping_version: int,
    baseline: BaselineConfig | None = None,
    gerado_em: datetime | None = None,
) -> dict[str, object]:
    """Relatório completo: versões, baseline, latência do fluxo `INVESTIGAR` e os 9 gates do `SPEC.md` §10."""
    baseline = baseline or load_baseline()
    gerado_em = gerado_em or datetime.now(UTC)
    latencias_totais_ms = [a.total_ms for a in amostras]
    latencias_llm_ms = [a.investigation_llm_ms for a in amostras if a.investigation_llm_ms is not None]
    gates = avalia_gates(latencias_totais_ms, baseline, auditoria_valida)

    overhead_s = None
    if latencias_llm_ms:
        p95_total_s = percentil(latencias_totais_ms, 95) / 1000
        overhead_s = p95_total_s - ADR_013_ESTIMATIVA_S

    return {
        "gerado_em": gerado_em.isoformat(),
        "amostra": {
            "tamanho": len(amostras),
            "alert_ids": [a.alert_id for a in amostras],
            "states_finais": [a.state_final for a in amostras],
        },
        "versoes": _versoes(amostras, rules_version, mapping_version),
        "baseline": {
            "tempo_manual_min": baseline.tempo_manual_min,
            "tempo_revisao_min": baseline.tempo_revisao_min,
        },
        "latencia_fluxo_investigar_ms": {
            "amostras": latencias_totais_ms,
            "p50": percentil(latencias_totais_ms, 50) if latencias_totais_ms else None,
            "p95": percentil(latencias_totais_ms, 95) if latencias_totais_ms else None,
        },
        "latencia_llm_ms": {
            "amostras": latencias_llm_ms,
            "p50": percentil(latencias_llm_ms, 50) if latencias_llm_ms else None,
            "p95": percentil(latencias_llm_ms, 95) if latencias_llm_ms else None,
        },
        "overhead_grafo_sobre_adr013_s": overhead_s,
        "adr013_estimativa_s": ADR_013_ESTIMATIVA_S,
        "gates": [asdict(g) for g in gates],
    }


def _linha_gate(g: dict[str, object]) -> str:
    aprovado = g["aprovado"]
    marca = "—" if aprovado is None else ("✅" if aprovado else "❌")
    valor = g["valor"] if g["valor"] is not None else "-"
    return f"| {g['metrica']} | {g['formula']} | {g['gate']} | {g['status']} | {valor} | {marca} |"


def _markdown(relatorio: dict[str, object]) -> str:
    v = relatorio["versoes"]
    lat_total = relatorio["latencia_fluxo_investigar_ms"]
    lat_llm = relatorio["latencia_llm_ms"]
    overhead = relatorio["overhead_grafo_sobre_adr013_s"]
    overhead_txt = f"{overhead:+.2f} s" if overhead is not None else "não medido (amostra sem chamada real ao LLM)"
    linhas = [
        "# Relatório de avaliação — M1 (T1.13)",
        "",
        f"Gerado em: {relatorio['gerado_em']}",
        f"Amostra: {relatorio['amostra']['tamanho']} alerta(s) sintético(s), fluxo `INVESTIGAR` via API-01.",
        "",
        "## Versões gravadas",
        "",
        f"- `rules_version`: {v['rules_version']}",
        f"- `mapping_version`: {v['mapping_version']}",
        f"- `features_version`: {v['features_version']}",
        f"- `prompt_version`: {v['prompt_version']}",
        f"- `model`: {v['model']}",
        f"- `corpus_version`: {v['corpus_version']}",
        "",
        "## Latência (RNF-03, informativa — amostra sintética, não o golden set)",
        "",
        f"- Fluxo `INVESTIGAR` completo (grafo): p50 = {lat_total['p50']:.0f} ms, p95 = {lat_total['p95']:.0f} ms"
        if lat_total["p50"] is not None
        else "- Fluxo `INVESTIGAR` completo (grafo): sem amostra",
        f"- Só a chamada LLM (evento `MODEL_CALLED`): p50 = {lat_llm['p50']:.0f} ms, p95 = {lat_llm['p95']:.0f} ms"
        if lat_llm["p50"] is not None
        else "- Só a chamada LLM: sem amostra (modelo simulado ou sem execução real)",
        f"- Overhead do grafo sobre os {relatorio['adr013_estimativa_s']:.1f} s estimados no ADR-013: {overhead_txt}",
        "",
        "## Gates Go/No-Go (`SPEC.md` §10)",
        "",
        "| Métrica | Fórmula | Gate | Status | Valor | Aprovado |",
        "| :--- | :--- | :--- | :--- | :--- | :---: |",
        *[_linha_gate(g) for g in relatorio["gates"]],
        "",
        'Gate marcado "não medida" nunca é "aprovado" — cada linha traz a nota com o motivo e o marco que '
        "fecha a medição (`TASKS.md` §5).",
        "",
    ]
    return "\n".join(linhas)


def escreve_relatorio(relatorio: dict[str, object], out_dir: Path, hoje: date | None = None) -> tuple[Path, Path]:
    """Grava `eval-<data>.json` e `.md` em `out_dir`; devolve os dois caminhos."""
    out_dir.mkdir(parents=True, exist_ok=True)
    hoje = hoje or datetime.now(UTC).date()
    base = out_dir / f"eval-{hoje.isoformat()}"
    json_path = base.with_suffix(".json")
    md_path = base.with_suffix(".md")
    json_path.write_text(json.dumps(relatorio, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(_markdown(relatorio), encoding="utf-8")
    return json_path, md_path
