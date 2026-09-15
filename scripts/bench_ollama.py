"""Benchmark de latência dos SLMs locais — gate do SPEC.md (RNF-03) e ADR-010.

Mede, no hardware local, a latência dos dois nós LLM do grafo:
- Investigação: SLM ~3B, ~800 tokens de entrada, até 150 de saída (orçamento p95 ≤ 12 s).
- Seleção de chunks: SLM ~1,5B, ~700 tokens de entrada, até 60 de saída (orçamento p95 ≤ 3 s).

Todos os prompts são sintéticos: alertas usam apenas tokens (`CPF_01`, `CONTA_01`) e os trechos
normativos são textos fictícios rotulados como tal. Nenhum dado pessoal nem texto de norma real.

Uso: python scripts/bench_ollama.py [--runs 10] [--out-dir reports] [--host http://localhost:11434]
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
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

NS = 1_000_000_000

# Orçamento do SPEC.md, seção 5 (segundos, p95).
DETERMINISTIC_BUDGET_S = 1.5 + 0.5 + 1.0
FLOW_MARGIN_S = 2.0
FLOW_LIMIT_S = 20.0

PAYMENT_TYPES = ["PIX", "TED", "ESPECIE_DEPOSITO", "ESPECIE_SAQUE", "CARTAO", "TRANSFERENCIA_INTERNACIONAL"]
SUSPICIOUS_TYPOLOGIES = [
    "Fan-Out", "Fan-In", "Cycle", "Bipartite", "Stacked Bipartite", "Scatter-Gather", "Gather-Scatter",
    "Layered Fan-In", "Layered Fan-Out", "Structuring", "Smurfing", "Over-Invoicing", "Deposit-Send",
    "Cash Withdrawal", "Single Large Transaction", "Behavioural Change 1", "Behavioural Change 2",
]


@dataclass
class NodeSpec:
    name: str
    model: str
    target_prompt_tokens: int
    num_predict: int
    budget_p95_s: float


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
    valid_json: bool


@dataclass
class NodeReport:
    spec: NodeSpec
    calibrated_size: int
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
            "valid_json_ratio": round(sum(r.valid_json for r in self.runs) / len(self.runs), 2),
            "budget_p95_s": self.spec.budget_p95_s,
            "passes": self.pct("total_s", 95) <= self.spec.budget_p95_s,
        }


def http_json(host: str, path: str, payload: dict | None = None, timeout: int = 600) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(host + path, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def investigation_prompt(n_tx: int, nonce: int) -> str:
    rng = random.Random(nonce)
    start = date(2026, 9, 1)
    lines = []
    for i in range(n_tx):
        day = start + timedelta(days=rng.randint(0, 13))
        amount = f"{rng.uniform(500, 9900):.2f}"
        lines.append(
            f"- tx-{i:04d} | {day.isoformat()} | R$ {amount} | {rng.choice(PAYMENT_TYPES)} | "
            f"origem CONTA_01 | destino CONTA_{rng.randint(2, 40):02d} | BR -> BR"
        )
    # Nonce no início impede reaproveitamento do cache de prompt do Ollama entre execuções.
    return (
        f"[execucao {nonce}] Voce e o no de Investigacao de um sistema PLD/FT. Dados ja sanitizados: "
        "identificadores pessoais aparecem apenas como tokens sinteticos.\n"
        "Responda SOMENTE com JSON no formato: {\"typology_hypothesis\": <uma de "
        f"{json.dumps(SUSPICIOUS_TYPOLOGIES + ['NENHUMA'])}>, \"confidence\": <0..1>, "
        "\"recommendation\": \"COMUNICAR\"|\"ARQUIVAR\"|\"INCONCLUSIVO\", "
        "\"evidence\": [{\"evidence_id\": str, \"source\": \"transaction\", \"ref\": <transaction_id>, "
        "\"description\": str}], \"rationale\": <ate 600 caracteres>}\n\n"
        f"Alerta ALR-{nonce:05d} | regra LEG-ESPECIE-FRAG-01 | titular CPF_01 | conta CONTA_01\n"
        "Triagem: detector de fragmentacao disparou; listas de restricao: pep=false, ceis=false, cnep=false.\n"
        "Transacoes da janela:\n" + "\n".join(lines)
    )


def selection_prompt(filler: int, nonce: int) -> str:
    passages = []
    for k in range(1, 9):
        body = " ".join(
            f"Texto ficticio de benchmark numero {k}.{j}, sem valor normativo, usado apenas para medir latencia."
            for j in range(filler)
        )
        passages.append(f"[chunk_id: FICT-{k:02d}] {body}")
    return (
        f"[execucao {nonce}] Voce e o no de Selecao de trechos. Hipotese de tipologia: Structuring.\n"
        "Escolha no maximo 3 chunk_id entre os trechos abaixo. Nao gere texto normativo.\n"
        "Responda SOMENTE com JSON: {\"chunk_ids\": [str], \"applicability\": <ate 300 caracteres>}\n\n"
        + "\n".join(passages)
    )


def generate(host: str, model: str, prompt: str, num_predict: int) -> dict:
    return http_json(host, "/api/generate", {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "keep_alive": "30m",
        "options": {"temperature": 0, "seed": 42, "num_predict": num_predict, "num_ctx": 2048},
    })


def calibrate(host: str, spec: NodeSpec, builder, initial: int) -> int:
    """Ajusta o tamanho do prompt até ficar a ±10% do alvo de tokens. Também serve de aquecimento."""
    size = initial
    for attempt in range(5):
        resp = generate(host, spec.model, builder(size, 90_000 + attempt), 1)
        count = resp.get("prompt_eval_count", 0)
        if count and abs(count - spec.target_prompt_tokens) <= 0.1 * spec.target_prompt_tokens:
            break
        size = max(1, round(size * spec.target_prompt_tokens / max(count, 1)))
    return size


def run_node(host: str, spec: NodeSpec, builder, initial: int, runs: int) -> NodeReport:
    size = calibrate(host, spec, builder, initial)
    report = NodeReport(spec=spec, calibrated_size=size)
    for i in range(runs):
        resp = generate(host, spec.model, builder(size, i + 1), spec.num_predict)
        try:
            json.loads(resp.get("response", ""))
            valid = True
        except json.JSONDecodeError:
            valid = False
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
            valid_json=valid,
        ))
        print(f"  {spec.name} run {i + 1}/{runs}: {report.runs[-1].total_s:.2f} s", flush=True)
    return report


def hardware_info() -> dict:
    info: dict[str, object] = {"os": platform.platform(), "python": platform.python_version()}
    if sys.platform == "win32":
        ps = (
            "$c=Get-CimInstance Win32_Processor|Select-Object -First 1;"
            "$r=[math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory/1GB,1);"
            "$g=(Get-CimInstance Win32_VideoController|ForEach-Object{$_.Name}) -join '; ';"
            "\"$($c.Name)|$($c.NumberOfCores)|$($c.NumberOfLogicalProcessors)|$r|$g\""
        )
        try:
            out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True,
                                 text=True, timeout=30, check=True).stdout.strip()
            cpu, cores, threads, ram, gpu = out.split("|", 4)
            info.update(cpu=cpu, cores=int(cores), threads=int(threads), ram_gb=float(ram), gpu=gpu)
        except (subprocess.SubprocessError, ValueError) as exc:
            info["hardware_error"] = str(exc)
    return info


def write_reports(out_dir: Path, meta: dict, reports: list[NodeReport]) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = meta["date"]
    summaries = {r.spec.name: r.summary() for r in reports}
    llm_p95 = sum(s["total_s_p95"] for s in summaries.values())
    flow_p95 = llm_p95 + DETERMINISTIC_BUDGET_S
    flow = {
        "llm_p95_sum_s": round(llm_p95, 2),
        "deterministic_budget_s": DETERMINISTIC_BUDGET_S,
        "estimated_flow_p95_s": round(flow_p95, 2),
        "passes_with_margin": flow_p95 + FLOW_MARGIN_S <= FLOW_LIMIT_S,
        "passes_limit": flow_p95 <= FLOW_LIMIT_S,
    }

    payload = {
        "meta": meta,
        "nodes": [{"spec": asdict(r.spec), "calibrated_size": r.calibrated_size, "summary": summaries[r.spec.name],
                   "runs": [asdict(x) for x in r.runs]} for r in reports],
        "flow": flow,
    }
    json_path = out_dir / f"benchmark-ollama-{stamp}.json"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    hw = meta["hardware"]
    ok = lambda b: "PASSA" if b else "NÃO PASSA"  # noqa: E731
    lines = [
        f"# Benchmark Ollama — {stamp}",
        "",
        "Gate do `SPEC.md` (RNF-03, seção 5) e ADR-010. Prompts 100% sintéticos, sem dado pessoal.",
        "",
        "## Ambiente",
        f"- CPU: {hw.get('cpu', 'n/d')} ({hw.get('cores', '?')} núcleos / {hw.get('threads', '?')} threads)",
        f"- RAM: {hw.get('ram_gb', 'n/d')} GB — GPU: {hw.get('gpu', 'n/d')}",
        f"- SO: {hw['os']} — Python {hw['python']} — Ollama {meta['ollama_version']}",
        f"- Parâmetros: temperature 0, seed 42, num_ctx 2048, format json, {meta['runs']} execuções medidas por nó "
        "(calibração/aquecimento descartados), nonce no início do prompt para evitar cache de prompt.",
        "",
        "## Resultado por nó",
        "",
        "| Nó | Modelo (digest) | Tokens in / out (média) | Prompt tok/s | Geração tok/s | p50 (s) | p95 (s) | Orçamento p95 (s) | JSON válido | Veredito |",
        "| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- |",
    ]
    for r in reports:
        s = summaries[r.spec.name]
        digest = meta["model_digests"].get(r.spec.model, "n/d")[:12]
        lines.append(
            f"| {r.spec.name} | `{r.spec.model}` ({digest}) | {s['prompt_tokens_mean']} / {s['output_tokens_mean']} | "
            f"{s['prompt_tps_mean']} | {s['gen_tps_mean']} | {s['total_s_p50']} | {s['total_s_p95']} | "
            f"{s['budget_p95_s']} | {int(s['valid_json_ratio'] * 100)}% | **{ok(s['passes'])}** |"
        )
    lines += [
        "",
        "## Fluxo completo (estimado)",
        f"- Soma p95 dos nós LLM: {flow['llm_p95_sum_s']} s + etapas determinísticas orçadas {DETERMINISTIC_BUDGET_S} s "
        f"= **{flow['estimated_flow_p95_s']} s**",
        f"- Limite 20 s: **{ok(flow['passes_limit'])}** — com margem de {FLOW_MARGIN_S} s: **{ok(flow['passes_with_margin'])}**",
        "- Somar p95 de nós é conservador (os piores casos raramente coincidem).",
        "",
        f"Dados brutos: `{json_path.name}`.",
    ]
    md_path = out_dir / f"benchmark-ollama-{stamp}.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path, json_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark de latência dos SLMs locais (gate RNF-03).")
    parser.add_argument("--host", default="http://localhost:11434")
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--out-dir", type=Path, default=Path("reports"))
    parser.add_argument("--investigation-model", default="qwen2.5:3b")
    parser.add_argument("--selection-model", default="qwen2.5:1.5b")
    args = parser.parse_args()

    try:
        version = http_json(args.host, "/api/version", timeout=10)["version"]
        tags = http_json(args.host, "/api/tags", timeout=10)
    except (urllib.error.URLError, KeyError) as exc:
        print(f"ERRO: Ollama indisponível em {args.host}: {exc}", file=sys.stderr)
        return 2
    digests = {m["name"]: m.get("digest", "") for m in tags.get("models", [])}
    for model in (args.investigation_model, args.selection_model):
        if model not in digests:
            print(f"ERRO: modelo {model} não encontrado; rode `ollama pull {model}`.", file=sys.stderr)
            return 2

    nodes = [
        (NodeSpec("Investigação", args.investigation_model, 800, 150, 12.0), investigation_prompt, 20),
        (NodeSpec("Seleção de chunks", args.selection_model, 700, 60, 3.0), selection_prompt, 4),
    ]
    reports = []
    for spec, builder, initial in nodes:
        print(f"Calibrando e medindo {spec.name} ({spec.model})...", flush=True)
        reports.append(run_node(args.host, spec, builder, initial, args.runs))

    meta = {
        "date": datetime.now(timezone.utc).date().isoformat(),
        "ollama_version": version,
        "model_digests": digests,
        "runs": args.runs,
        "hardware": hardware_info(),
    }
    md_path, json_path = write_reports(args.out_dir, meta, reports)
    print(f"Relatório: {md_path}\nDados: {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
