"""Os 9 gates Go/No-Go do `SPEC.md` §10 medidos sobre o golden set real (`--golden`), fechando o gap registrado
em `MEMORY.md` ("M7 · gap conhecido"). Reaproveita `gate_velocidade`/`gate_latencia`/`gate_auditoria` de
`eval/gates.py` (mesma fórmula, agora sobre a amostra de 500 alertas em vez da amostra sintética do T1.13).
"""

from __future__ import annotations

from aml_guardian.config.baseline import BaselineConfig
from aml_guardian.eval.gates import (
    MEDIDA,
    NAO_MEDIDA,
    GateResultado,
    gate_auditoria,
    gate_latencia,
    gate_velocidade,
    percentil,
)
from aml_guardian.eval.golden_runner import AmostraGolden


def _gate_recall(amostras: list[AmostraGolden]) -> GateResultado:
    criticos = [a for a in amostras if a.critica]
    if not criticos:
        return GateResultado(
            "Recall crítico",
            "RNF-01",
            "= 100%",
            NAO_MEDIDA,
            None,
            None,
            "Nenhum alerta crítico na amostra rodada (ver --limit).",
        )
    ok = sum(1 for a in criticos if a.state_final == "NEEDS_HUMAN" or a.dossier_type == "COS")
    recall = ok / len(criticos)
    return GateResultado(
        metrica="Recall crítico",
        formula="RNF-01",
        gate="= 100%",
        status=MEDIDA,
        valor=f"{recall:.2%}",
        aprovado=recall >= 1.0,
        nota=f"{ok}/{len(criticos)} alertas críticos do golden terminaram COS/NEEDS_HUMAN (nunca ARQUIVAMENTO). "
        "Cache semântico não está implementado nesta PoC (nenhum módulo de cache em src/), então a rodada já "
        "é 'cache desligado' por construção, como o RNF-01 exige.",
    )


def _gate_grounding(amostras: list[AmostraGolden]) -> GateResultado:
    com_proposta = [a for a in amostras if a.citations_propostas > 0]
    if not com_proposta:
        return GateResultado(
            "Grounding",
            "RNF-02",
            "bruto ≥ 99% e final 0",
            NAO_MEDIDA,
            None,
            None,
            "Nenhum alerta da amostra propôs citação (ver --limit ou cobertura do mapping).",
        )
    total_proposto = sum(a.citations_propostas for a in com_proposta)
    total_verificado = sum(a.citations_verificadas for a in com_proposta)
    bruto = total_verificado / total_proposto
    aprovado = bruto >= 0.99  # final = 0 não verificadas é garantido por construção (Dossier só usa verified_citations)
    return GateResultado(
        metrica="Grounding",
        formula="RNF-02",
        gate="bruto ≥ 99% e final 0",
        status=MEDIDA,
        valor=f"bruto {bruto:.2%}, final 0",
        aprovado=aprovado,
        nota=f"{len(com_proposta)}/{len(amostras)} alertas propuseram citação — só `Structuring` tem "
        "`applicability` curado em `data/mappings/saml_d_to_cc4001.yaml` (mapping_version 2); as demais 16 "
        "tipologias não propõem citação por desenho (RF-06), não entram no denominador do bruto. Final = 0 "
        "não verificadas é garantido pelo assembler (`dossier/assembler.py` só usa `verified_citations`), não "
        "recontado aqui para não duplicar evidência do Revisor (T1.8).",
    )


def _gate_fp(amostras: list[AmostraGolden]) -> GateResultado:
    normais = [a for a in amostras if a.normal]
    if not normais:
        return GateResultado(
            "Redução de falsos positivos",
            "1 − FP_pipeline / FP_baseline",
            "≥ 65%",
            NAO_MEDIDA,
            None,
            None,
            "Nenhum alerta normal (não laundering) na amostra rodada (ver --limit).",
        )
    fp_pipeline = sum(1 for a in normais if a.state_final == "NEEDS_HUMAN" or a.dossier_type == "COS")
    fp_baseline = len(normais)  # SPEC.md §10: "FP_baseline = alertas normais do golden set (legado encaminha 100%)"
    reducao = 1 - fp_pipeline / fp_baseline
    return GateResultado(
        metrica="Redução de falsos positivos",
        formula="1 − FP_pipeline / FP_baseline",
        gate="≥ 65%",
        status=MEDIDA,
        valor=f"{reducao:.2%}",
        aprovado=reducao >= 0.65,
        nota=f"FP_pipeline = {fp_pipeline}/{fp_baseline} alertas normais do golden terminaram COS/NEEDS_HUMAN "
        "(deveriam ser ARQUIVAMENTO); FP_baseline = 100% (legado T0.8 encaminha todo alerta que gera, "
        "SPEC.md §10, fórmula literal — não é escolha nova desta tarefa).",
    )


def _gate_tokens(amostras: list[AmostraGolden]) -> GateResultado:
    chamados = [a for a in amostras if (a.tokens_in + a.tokens_out) > 0]
    if not chamados:
        return GateResultado(
            "Redução de tokens",
            "SPEC.md §3.3",
            "> 70%",
            NAO_MEDIDA,
            None,
            None,
            "Nenhum alerta da amostra chamou o LLM (ver --limit ou --ollama).",
        )
    tokens_pipeline_total = sum(a.tokens_in + a.tokens_out for a in amostras)
    media_por_chamada = sum(a.tokens_in + a.tokens_out for a in chamados) / len(chamados)
    tokens_baseline_total = media_por_chamada * len(amostras)
    reducao = 1 - tokens_pipeline_total / tokens_baseline_total
    return GateResultado(
        metrica="Redução de tokens",
        formula="SPEC.md §3.3: 1 − tokens_pipeline / tokens_baseline",
        gate="> 70%",
        status=MEDIDA,
        valor=f"{reducao:.2%}",
        aprovado=reducao > 0.70,
        nota=f"tokens_pipeline = soma real dos {len(chamados)}/{len(amostras)} alertas que chamaram o LLM "
        "(triagem evita chamada nos demais, `PROPOR_ARQUIVAMENTO`); tokens_baseline = média real por chamada × "
        f"{len(amostras)}, o contrafactual '100% via agentes' do SPEC.md §3.3 sem rodar o golden set uma segunda "
        "vez com triagem desligada — decisão de menor custo (MEMORY.md), pois cache semântico não está "
        "implementado nesta PoC (já é 'cache desligado' em toda rodada) e a única variável restante é a "
        "triagem, cujo efeito é medido diretamente pela fração de alertas que evitou o LLM.",
    )


def _gate_prazo(amostras: list[AmostraGolden]) -> GateResultado:
    com_dossie = [a for a in amostras if a.prazo_ok is not None]
    if not com_dossie:
        return GateResultado(
            "Prazo interno",
            "SPEC.md §3.1",
            "100% dentro",
            NAO_MEDIDA,
            None,
            None,
            "Nenhum alerta da amostra chegou a ter dossiê (ver --limit).",
        )
    ok = sum(1 for a in com_dossie if a.prazo_ok)
    cobertura = ok / len(com_dossie)
    return GateResultado(
        metrica="Prazo interno",
        formula="SPEC.md §3.1",
        gate="100% dentro",
        status=MEDIDA,
        valor=f"{cobertura:.2%}",
        aprovado=cobertura >= 1.0,
        nota="Proxy de cobertura: fração de dossiês com `prazo_interno`/`prazo_regulatorio_analise` (DT-11) "
        "calculados e em ordem cronológica com `selecao_em`. A métrica literal do SPEC §3.1 (chegada em "
        "DRAFT_READY dentro do prazo em relação ao tempo real decorrido) não se aplica a uma rodada em lote "
        "único executada em minutos/horas — mesma ressalva já registrada em `gates.py::_gate_prazo` (T1.13).",
    )


def _gate_privacidade(limpo: bool, ocorrencias: int) -> GateResultado:
    return GateResultado(
        metrica="Privacidade",
        formula="RNF-05",
        gate="0 ocorrências",
        status=MEDIDA,
        valor=f"{ocorrencias} ocorrência(s)",
        aprovado=limpo,
        nota="Varredura de CPF/CNPJ sintético dos payloads golden efetivamente rodados sobre `audit_events` + "
        "`alert_records` desta execução (mesma técnica de `tests/privacy/test_canary.py`, T1.12). Prompt "
        "capturado do LiteLLM não repetido aqui (já coberto pelo canário unitário); terceiro destino (logs) "
        "continua não medido, como no T1.12 (sem infraestrutura de log formada).",
    )


def avalia_gates_golden(
    amostras: list[AmostraGolden],
    baseline: BaselineConfig,
    auditoria_valida: bool,
    privacidade_limpo: bool,
    privacidade_ocorrencias: int,
) -> list[GateResultado]:
    """Todos os 9 gates do `SPEC.md` §10, agora medidos sobre o golden set real (`data/golden/v1`, 500 alertas
    ou o subconjunto de `--limit`)."""
    if not amostras:
        raise ValueError("avalia_gates_golden requer ao menos uma amostra")
    latencias_ms = [a.total_ms for a in amostras]
    media_ms = sum(latencias_ms) / len(latencias_ms)
    p95_ms = percentil(latencias_ms, 95)
    latencia_media_min = (media_ms / 1000) / 60
    return [
        _gate_recall(amostras),
        _gate_grounding(amostras),
        _gate_fp(amostras),
        gate_velocidade(latencia_media_min, baseline),
        _gate_tokens(amostras),
        gate_latencia(p95_ms),
        _gate_prazo(amostras),
        _gate_privacidade(privacidade_limpo, privacidade_ocorrencias),
        gate_auditoria(auditoria_valida),
    ]
