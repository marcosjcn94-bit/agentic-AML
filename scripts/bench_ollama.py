"""Benchmark de latência dos SLMs locais — gate do SPEC.md (RNF-03), ADR-010 e ADR-013.

Mede, no hardware local, a latência do único nó LLM do grafo após o ADR-013:
- Investigação: SLM ~1,5B, ~300 tokens de entrada (indicadores agregados, DT-16), até 60 de saída
  imposta por JSON Schema (DT-07), orçamento p95 ≤ 14 s.
A Seleção de chunks passou a ser determinística (ADR-013) e entra no orçamento das etapas determinísticas.

Modos medidos:
- prefixo frio (gate): nonce no início do prompt, sem reaproveitamento do KV cache do Ollama;
- prefixo estável (informativo): instruções fixas primeiro, como em produção entre alertas consecutivos.
A varredura opcional de `num_thread` (ADR-013, opção C) escolhe o melhor valor pelo p50 antes das medições.

Todos os prompts são sintéticos: alertas usam apenas tokens (`CPF_01`, `CONTA_01`) e os indicadores
são valores aleatórios com semente. Nenhum dado pessoal nem texto de norma real.

Uso: python scripts/bench_ollama.py [--runs 10] [--thread-sweep auto,4,6,8,10,12] [--tag v2]
     [--out-dir reports] [--host http://localhost:11434]
Somente biblioteca padrão.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import random
import statistics
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

NS = 1_000_000_000

# Orçamento do SPEC.md, seção 5 (segundos, p95), revisado pelo ADR-013:
# sanitização/triagem/MCP/indicadores + embedding/busca + seleção determinística + revisor/template/auditoria.
DETERMINISTIC_BUDGET_S = 1.5 + 0.5 + 0.5 + 1.0
FLOW_MARGIN_S = 2.5
FLOW_LIMIT_S = 20.0

SUSPICIOUS_TYPOLOGIES = [
    "Fan-Out", "Fan-In", "Cycle", "Bipartite", "Stacked Bipartite", "Scatter-Gather", "Gather-Scatter",
    "Layered Fan-In", "Layered Fan-Out", "Structuring", "Smurfing", "Over-Invoicing", "Deposit-Send",
    "Cash Withdrawal", "Single Large Transaction", "Behavioural Change 1", "Behavioural Change 2",
]
RECOMMENDATIONS = ["COMUNICAR", "ARQUIVAR", "INCONCLUSIVO"]
MAX_EVIDENCE = 3

# Chaves curtas na geração reduzem tokens de saída; o código expande para os campos do DT-07 (ADR-013).
OUTPUT_KEYS = {"t": "typology_hypothesis", "c": "confidence", "r": "recommendation", "e": "evidence_feature_ids"}

INVESTIGATION_INSTRUCTIONS = (
    "No de Investigacao PLD/FT. Dados sanitizados: pessoas e contas so como tokens sinteticos.\n"
    "Responda JSON: t=tipologia mais provavel ou NENHUMA; c=confianca 0-1; r=recomendacao; "
    f"e=ate {MAX_EVIDENCE} numeros de feature que sustentam t (F03 -> 3).\n"
)

Builder = Callable[[int, int], tuple[str, list[str]]]


@dataclass
class NodeSpec:
    name: str
    model: str
    target_prompt_tokens: int
    num_predict: int
    budget_p95_s: float
    gate: bool = True


@dataclass
class RunResult:
    run: int
    prompt_tokens: int
    output_tokens: int
    prompt_eval_s: float
    eval_s: float
    load_s: float
    total_s: float
    prompt_tps: float
    gen_tps: float
    valid_schema: bool


@dataclass
class NodeReport:
    spec: NodeSpec
    calibrated_size: int
    num_thread: int | None
    runs: list[RunResult] = field(default_factory=list)

    def pct(self, attr: str, p: float) -> float:
        values = sorted(getattr(r, attr) for r in self.runs)
        # Percentil pelo método nearest-rank (conservador para amostras pequenas).
        return values[max(0, math.ceil(p / 100 * len(values)) - 1)]

    def summary(self) -> dict:
        return {
            "total_s_p50": round(self.pct("total_s", 50), 2),
            "total_s_p95": round(self.pct("total_s", 95), 2),
            "prompt_tps_mean": round(statistics.mean(r.prompt_tps for r in self.runs), 1),
            "gen_tps_mean": round(statistics.mean(r.gen_tps for r in self.runs), 1),
            "prompt_tokens_mean": round(statistics.mean(r.prompt_tokens for r in self.runs)),
            "output_tokens_mean": round(statistics.mean(r.output_tokens for r in self.runs)),
            "valid_schema_ratio": round(sum(r.valid_schema for r in self.runs) / len(self.runs), 2),
            "budget_p95_s": self.spec.budget_p95_s,
            "passes": self.pct("total_s", 95) <= self.spec.budget_p95_s,
        }


def http_json(host: str, path: str, payload: dict | None = None, timeout: int = 600) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(host + path, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def investigation_features(n_counterparties: int, nonce: int) -> dict[str, str]:
    """Indicadores sintéticos no formato do DT-16 (feature_id → valor legível)."""
    rng = random.Random(nonce)
    # Nomes curtos e valores inteiros: no tokenizador do Qwen cada dígito custa um token.
    features = {
        "F01": f"tx_janela={rng.randint(8, 40)}",
        "F02": f"total_brl={rng.randint(20_000, 250_000)}",
        "F03": f"abaixo_limiar={rng.randint(0, 15)}",
        "F04": f"dep_especie={rng.randint(0, 12)}",
        "F05": f"saida_pix_ted={rng.randint(0, 20)}",
        "F06": f"contrap_entrada={rng.randint(1, 25)}",
        "F07": f"contrap_saida={rng.randint(1, 25)}",
        "F08": f"camadas={rng.randint(0, 3)}",
        "F09": f"transfronteira={rng.randint(0, 4)}",
        "F10": f"especie_depois_exterior={rng.choice(['sim', 'nao'])}",
        "F11": f"vol_vs_media180d={rng.uniform(0.5, 9):.1f}x",
        "F12": f"dias_ativos={rng.randint(1, 14)}",
        "F13": "listas=pep:nao,ceis:nao,cnep:nao",
    }
    for k in range(n_counterparties):
        features[f"F{14 + k:02d}"] = (
            f"CONTA_{k + 2:02d} in={rng.randint(0, 6)} out={rng.randint(0, 6)} brl={rng.randint(500, 30_000)}"
        )
    return features


def investigation_prompt(n_counterparties: int, nonce: int, stable_prefix: bool = False) -> tuple[str, list[str]]:
    features = investigation_features(n_counterparties, nonce)
    alert = (
        f"Alerta ALR-{nonce:05d} regra LEG-ESPECIE-FRAG-01 titular CPF_01 conta CONTA_01\n"
        "Triagem: fragmentacao disparou.\nIndicadores:\n"
        + "\n".join(f"{fid} {value}" for fid, value in features.items())
    )
    if stable_prefix:
        # Instruções fixas primeiro: o Ollama reaproveita o KV cache do prefixo entre alertas consecutivos.
        return INVESTIGATION_INSTRUCTIONS + alert, list(features)
    # Nonce no início impede reaproveitamento do cache de prompt do Ollama entre execuções.
    return f"[execucao {nonce}] " + INVESTIGATION_INSTRUCTIONS + alert, list(features)


def investigation_schema(feature_ids: list[str]) -> dict:
    """JSON Schema de geração do DT-07 (revisão ADR-013), com chaves curtas, imposto pelo Ollama."""
    return {
        "type": "object",
        "properties": {
            "t": {"type": "string", "enum": SUSPICIOUS_TYPOLOGIES + ["NENHUMA"]},
            "c": {"type": "number", "minimum": 0, "maximum": 1},
            "r": {"type": "string", "enum": RECOMMENDATIONS},
            # Evidência como número da feature (F03 -> 3); reduz tokens de saída.
            "e": {"type": "array", "items": {"type": "integer", "enum": [int(f[1:]) for f in feature_ids]},
                  "maxItems": MAX_EVIDENCE},
        },
        "required": list(OUTPUT_KEYS),
    }


def validate_output(text: str, feature_ids: list[str]) -> bool:
    """Expande as chaves curtas para o DT-07 e valida como o pós-processamento determinístico do RF-05."""
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        return False
    if not isinstance(raw, dict) or set(raw) != set(OUTPUT_KEYS) or not isinstance(raw["e"], list):
        return False
    if not all(isinstance(n, int) and not isinstance(n, bool) for n in raw["e"]):
        return False
    out = {OUTPUT_KEYS[k]: v for k, v in raw.items()}
    out["evidence_feature_ids"] = [f"F{n:02d}" for n in raw["e"]]
    evidence = out.get("evidence_feature_ids")
    confidence = out.get("confidence")
    return (
        out.get("typology_hypothesis") in SUSPICIOUS_TYPOLOGIES + ["NENHUMA"]
        and isinstance(confidence, (int, float)) and 0 <= confidence <= 1
        and out.get("recommendation") in RECOMMENDATIONS
        and isinstance(evidence, list) and len(evidence) <= MAX_EVIDENCE
        and all(e in feature_ids for e in evidence)
    )


def generate(host: str, model: str, prompt: str, num_predict: int, fmt: dict | str,
             num_thread: int | None) -> dict:
    options: dict[str, object] = {"temperature": 0, "seed": 42, "num_predict": num_predict, "num_ctx": 2048}
    if num_thread is not None:
        options["num_thread"] = num_thread
    return http_json(host, "/api/generate", {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": fmt,
        "keep_alive": "30m",
        "options": options,
    })


def calibrate(host: str, spec: NodeSpec, builder: Builder, initial: int) -> int:
    """Ajusta o tamanho do prompt até ficar a ±10% do alvo de tokens."""
    size = initial
    for attempt in range(5):
        prompt, _ = builder(size, 90_000 + attempt)
        count = generate(host, spec.model, prompt, 1, "json", None).get("prompt_eval_count", 0)
        if count and abs(count - spec.target_prompt_tokens) <= 0.1 * spec.target_prompt_tokens:
            break
        # Cada contraparte extra adiciona ~20 tokens; o ajuste converge em poucas tentativas.
        size = max(0, size + round((spec.target_prompt_tokens - count) / 20))
    return size


def run_node(host: str, spec: NodeSpec, builder: Builder, size: int, runs: int, num_thread: int | None,
             nonce_offset: int = 0, verbose: bool = True) -> NodeReport:
    report = NodeReport(spec=spec, calibrated_size=size, num_thread=num_thread)
    # Aquecimento descartado: carrega o modelo e prepara o cache estável.
    warm_prompt, warm_ids = builder(size, 80_000 + nonce_offset)
    generate(host, spec.model, warm_prompt, spec.num_predict, investigation_schema(warm_ids), num_thread)
    for i in range(runs):
        prompt, feature_ids = builder(size, nonce_offset + i + 1)
        resp = generate(host, spec.model, prompt, spec.num_predict, investigation_schema(feature_ids), num_thread)
        pe_s = resp.get("prompt_eval_duration", 0) / NS
        ev_s = resp.get("eval_duration", 0) / NS
        pc = resp.get("prompt_eval_count", 0)
        oc = resp.get("eval_count", 0)
        report.runs.append(RunResult(
            run=i + 1,
            prompt_tokens=pc,
            output_tokens=oc,
            prompt_eval_s=round(pe_s, 3),
            eval_s=round(ev_s, 3),
            load_s=round(resp.get("load_duration", 0) / NS, 3),
            total_s=round(resp.get("total_duration", 0) / NS, 3),
            prompt_tps=round(pc / pe_s, 1) if pe_s else 0.0,
            gen_tps=round(oc / ev_s, 1) if ev_s else 0.0,
            valid_schema=validate_output(resp.get("response", ""), feature_ids),
        ))
        if verbose:
            print(f"  {spec.name} run {i + 1}/{runs}: {report.runs[-1].total_s:.2f} s", flush=True)
    return report


def sweep_threads(host: str, spec: NodeSpec, builder: Builder, size: int, candidates: list[int | None],
                  runs: int) -> list[dict]:
    rows = []
    for idx, threads in enumerate(candidates):
        label = "auto" if threads is None else str(threads)
        rep = run_node(host, spec, builder, size, runs, threads, nonce_offset=10_000 * (idx + 1), verbose=False)
        s = rep.summary()
        rows.append({"num_thread": threads, "label": label, "total_s_p50": s["total_s_p50"],
                     "prompt_tps_mean": s["prompt_tps_mean"], "gen_tps_mean": s["gen_tps_mean"]})
        print(f"  num_thread={label}: p50 {s['total_s_p50']:.2f} s | prompt {s['prompt_tps_mean']} tok/s | "
              f"geração {s['gen_tps_mean']} tok/s", flush=True)
    return rows


def hardware_info() -> dict:
    info: dict[str, object] = {"os": platform.platform(), "python": platform.python_version()}
    if sys.platform == "win32":
        ps = (
            "$c=Get-CimInstance Win32_Processor|Select-Object -First 1;"
            "$r=[math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory/1GB,1);"
            "$g=(Get-CimInstance Win32_VideoController|ForEach-Object{$_.Name}) -join '; ';"
            "$b=(Get-CimInstance Win32_Battery|Select-Object -First 1).BatteryStatus;"
            "\"$($c.Name)|$($c.NumberOfCores)|$($c.NumberOfLogicalProcessors)|$r|$b|$g\""
        )
        try:
            out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True,
                                 text=True, timeout=30, check=True).stdout.strip()
            cpu, cores, threads, ram, battery, gpu = out.split("|", 5)
            # Win32_Battery.BatteryStatus = 2 indica alimentação pela tomada.
            info.update(cpu=cpu, cores=int(cores), threads=int(threads), ram_gb=float(ram), gpu=gpu,
                        ac_power=battery.strip() in ("", "2"))
            scheme = subprocess.run(["powercfg", "/getactivescheme"], capture_output=True, text=True,
                                    timeout=30, check=True).stdout.strip()
            info["power_scheme"] = scheme.split("(", 1)[-1].rstrip(")") if "(" in scheme else scheme
        except (subprocess.SubprocessError, ValueError, OSError) as exc:
            info["hardware_error"] = str(exc)
    return info


def write_reports(out_dir: Path, meta: dict, reports: list[NodeReport], sweep: list[dict]) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = meta["date"] + (f"-{meta['tag']}" if meta["tag"] else "")
    summaries = {r.spec.name: r.summary() for r in reports}
    llm_p95 = sum(summaries[r.spec.name]["total_s_p95"] for r in reports if r.spec.gate)
    flow_p95 = llm_p95 + DETERMINISTIC_BUDGET_S
    flow = {
        "llm_p95_sum_s": round(llm_p95, 2),
        "deterministic_budget_s": DETERMINISTIC_BUDGET_S,
        "estimated_flow_p95_s": round(flow_p95, 2),
        "passes_with_margin": flow_p95 + FLOW_MARGIN_S <= FLOW_LIMIT_S,
        "passes_limit": flow_p95 < FLOW_LIMIT_S,
    }

    payload = {
        "meta": meta,
        "thread_sweep": sweep,
        "nodes": [{"spec": asdict(r.spec), "calibrated_size": r.calibrated_size, "num_thread": r.num_thread,
                   "summary": summaries[r.spec.name], "runs": [asdict(x) for x in r.runs]} for r in reports],
        "flow": flow,
    }
    json_path = out_dir / f"benchmark-ollama-{stamp}.json"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    hw = meta["hardware"]
    ok = lambda b: "PASSA" if b else "NÃO PASSA"  # noqa: E731
    chosen = "auto" if meta["num_thread"] is None else meta["num_thread"]
    lines = [
        f"# Benchmark Ollama — {stamp}",
        "",
        "Gate do `SPEC.md` (RNF-03, seção 5), ADR-010 e ADR-013. Prompts 100% sintéticos, sem dado pessoal.",
        "",
        "## Ambiente",
        f"- CPU: {hw.get('cpu', 'n/d')} ({hw.get('cores', '?')} núcleos / {hw.get('threads', '?')} threads)",
        f"- RAM: {hw.get('ram_gb', 'n/d')} GB — GPU: {hw.get('gpu', 'n/d')}",
        f"- Energia: {'tomada' if hw.get('ac_power') else 'bateria'} — plano `{hw.get('power_scheme', 'n/d')}`",
        f"- SO: {hw['os']} — Python {hw['python']} — Ollama {meta['ollama_version']}",
        f"- Parâmetros: temperature 0, seed 42, num_ctx 2048, saída por JSON Schema (DT-07), num_thread {chosen}, "
        f"{meta['runs']} execuções medidas por nó (calibração/aquecimento descartados).",
        "",
    ]
    if sweep:
        lines += [
            f"## Varredura de num_thread ({meta['sweep_runs']} execuções por valor, prefixo frio)",
            "",
            "| num_thread | p50 (s) | Prompt tok/s | Geração tok/s |",
            "| :--- | ---: | ---: | ---: |",
        ]
        lines += [f"| {row['label']} | {row['total_s_p50']} | {row['prompt_tps_mean']} | {row['gen_tps_mean']} |"
                  for row in sweep]
        lines += ["", f"Escolhido pelo menor p50: **{chosen}**.", ""]
    lines += [
        "## Resultado por nó",
        "",
        "| Nó | Modelo | Tokens in/out | Prompt tok/s | Geração tok/s | p50 | p95 | Budget | Schema | Veredito |",
        "| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- |",
    ]
    for r in reports:
        s = summaries[r.spec.name]
        digest = meta["model_digests"].get(r.spec.model, "n/d")[:12]
        verdict = f"**{ok(s['passes'])}**" if r.spec.gate else f"informativo ({ok(s['passes'])})"
        lines.append(
            f"| {r.spec.name} | `{r.spec.model}` ({digest}) | {s['prompt_tokens_mean']} / {s['output_tokens_mean']} | "
            f"{s['prompt_tps_mean']} | {s['gen_tps_mean']} | {s['total_s_p50']} | {s['total_s_p95']} | "
            f"{s['budget_p95_s']} | {int(s['valid_schema_ratio'] * 100)}% | {verdict} |"
        )
    lines += [
        "",
        "## Fluxo completo (estimado)",
        f"- p95 LLM: {flow['llm_p95_sum_s']} s + etapas determinísticas {DETERMINISTIC_BUDGET_S} s "
        f"(inclui Seleção de chunks determinística, ADR-013) = **{flow['estimated_flow_p95_s']} s**",
        f"- Limite < {FLOW_LIMIT_S:g} s: **{ok(flow['passes_limit'])}** — com margem de {FLOW_MARGIN_S} s: "
        f"**{ok(flow['passes_with_margin'])}**",
        "- As etapas determinísticas entram pelo orçamento do SPEC; são medidas nos testes de avaliação (seção 10).",
        "",
        f"Dados brutos: `{json_path.name}`.",
    ]
    md_path = out_dir / f"benchmark-ollama-{stamp}.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path, json_path


def parse_threads(value: str) -> list[int | None]:
    return [None if v.strip() == "auto" else int(v) for v in value.split(",") if v.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark de latência dos SLMs locais (gate RNF-03, ADR-013).")
    parser.add_argument("--host", default="http://localhost:11434")
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--out-dir", type=Path, default=Path("reports"))
    parser.add_argument("--investigation-model", default="qwen2.5:1.5b")
    parser.add_argument("--num-thread", type=int, default=None, help="Fixa num_thread (ignorado com --thread-sweep).")
    parser.add_argument("--thread-sweep", type=parse_threads, default=None,
                        help="Lista de num_thread a comparar, ex.: auto,4,6,8,10,12.")
    parser.add_argument("--sweep-runs", type=int, default=3)
    parser.add_argument("--tag", default="", help="Sufixo do nome do relatório, ex.: v2.")
    args = parser.parse_args()

    try:
        version = http_json(args.host, "/api/version", timeout=10)["version"]
        tags = http_json(args.host, "/api/tags", timeout=10)
    except (urllib.error.URLError, KeyError) as exc:
        print(f"ERRO: Ollama indisponível em {args.host}: {exc}", file=sys.stderr)
        return 2
    digests = {m["name"]: m.get("digest", "") for m in tags.get("models", [])}
    if args.investigation_model not in digests:
        print(f"ERRO: modelo {args.investigation_model} não encontrado; rode `ollama pull {args.investigation_model}`.",
              file=sys.stderr)
        return 2

    cold = NodeSpec("Investigação", args.investigation_model, 300, 60, 14.0)
    warm = NodeSpec("Investigação (prefixo estável)", args.investigation_model, 300, 60, 14.0, gate=False)
    cold_builder: Builder = investigation_prompt
    warm_builder: Builder = partial(investigation_prompt, stable_prefix=True)

    print(f"Calibrando prompt de {cold.name} ({cold.model})...", flush=True)
    size = calibrate(args.host, cold, cold_builder, initial=0)

    sweep: list[dict] = []
    num_thread = args.num_thread
    if args.thread_sweep:
        print("Varredura de num_thread...", flush=True)
        sweep = sweep_threads(args.host, cold, cold_builder, size, args.thread_sweep, args.sweep_runs)
        num_thread = min(sweep, key=lambda row: row["total_s_p50"])["num_thread"]

    reports = []
    for spec, builder in ((cold, cold_builder), (warm, warm_builder)):
        print(f"Medindo {spec.name} (num_thread={'auto' if num_thread is None else num_thread})...", flush=True)
        reports.append(run_node(args.host, spec, builder, size, args.runs, num_thread))

    meta = {
        "date": datetime.now(UTC).date().isoformat(),
        "tag": args.tag,
        "ollama_version": version,
        "model_digests": digests,
        "runs": args.runs,
        "sweep_runs": args.sweep_runs if sweep else 0,
        "num_thread": num_thread,
        "hardware": hardware_info(),
    }
    md_path, json_path = write_reports(args.out_dir, meta, reports, sweep)
    print(f"Relatório: {md_path}\nDados: {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
