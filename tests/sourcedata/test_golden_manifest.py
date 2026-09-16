from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from aml_guardian.contracts.ingestion import (
    Alert,
    OccurrenceWindow,
    PaymentType,
    SenderCustomer,
    Transaction,
)
from aml_guardian.sourcedata.golden_manifest import (
    GoldenSetError,
    carrega_manifesto,
    constroi_manifesto,
    grava_golden,
    payload_sha256,
)

MANIFESTO_REAL = Path(__file__).resolve().parents[2] / "data" / "golden" / "v1" / "manifest.json"


def _tx(indice: int) -> Transaction:
    return Transaction(
        transaction_id=f"tx-{indice:04d}",
        timestamp=datetime(2023, 1, indice, tzinfo=UTC),
        amount_brl="100.00",
        payment_type=PaymentType.PIX,
        sender_account="conta-1",
        receiver_account="conta-2",
        sender_location="BR",
        receiver_location="BR",
        currency_sent="BRL",
        currency_received="BRL",
    )


def _alerta(transacoes: list[Transaction]) -> Alert:
    return Alert(
        alert_id=uuid.uuid4(),
        source_rule_id="teste",
        selected_at=transacoes[-1].timestamp,
        occurrence_window=OccurrenceWindow(start=transacoes[0].timestamp, end=transacoes[-1].timestamp),
        sender_account="conta-1",
        sender_customer=SenderCustomer(name="Cliente Teste", cpf_cnpj="CPF_01"),
        transactions=transacoes,
    )


def _manifesto_base(selecionados=None):
    """`selecionados` fixo por parâmetro (não regerado a cada chamada) para permitir comparar hashes entre
    duas construções da MESMA seleção — `_alerta` sorteia um `alert_id` novo a cada chamada."""
    if selecionados is None:
        selecionados = [(_alerta([_tx(1)]), "Structuring")]
    manifesto = constroi_manifesto(
        selecionados,
        core_sintetico_sha256="a" * 64,
        alert_rules_version=1,
        mapping_version=1,
        seed=42,
        disponibilidade_por_estrato={"Structuring": 5},
    )
    return manifesto, selecionados


def test_payload_sha256_estavel_para_o_mesmo_alerta():
    alerta = _alerta([_tx(1)])
    assert payload_sha256(alerta) == payload_sha256(alerta)
    assert len(payload_sha256(alerta)) == 64


def test_constroi_manifesto_hash_reproduz_para_a_mesma_selecao():
    m1, selecionados = _manifesto_base()
    m2, _ = _manifesto_base(selecionados)
    assert m1.manifest_sha256 == m2.manifest_sha256
    assert m1.contagem_por_estrato == {"Structuring": 1}
    assert m1.disponibilidade_por_estrato == {"Structuring": 5}


def test_constroi_manifesto_hash_muda_se_a_selecao_muda():
    base, _ = _manifesto_base()
    outro_alerta = _alerta([_tx(1)]).model_copy(update={"alert_id": uuid.uuid4()})
    diferente = constroi_manifesto(
        [(outro_alerta, "Structuring")],
        core_sintetico_sha256="a" * 64,
        alert_rules_version=1,
        mapping_version=1,
        seed=42,
        disponibilidade_por_estrato={"Structuring": 5},
    )
    assert base.manifest_sha256 != diferente.manifest_sha256


def test_constroi_manifesto_hash_muda_se_a_disponibilidade_muda():
    base, selecionados = _manifesto_base()
    outro = constroi_manifesto(
        selecionados,
        core_sintetico_sha256="a" * 64,
        alert_rules_version=1,
        mapping_version=1,
        seed=42,
        disponibilidade_por_estrato={"Structuring": 999},
    )
    assert base.manifest_sha256 != outro.manifest_sha256


def test_grava_e_carrega_manifesto_ida_e_volta(tmp_path):
    manifesto, selecionados = _manifesto_base()
    destino = tmp_path / "v1"
    grava_golden(destino, manifesto, selecionados)
    assert (destino / "manifest.json").exists()
    payload_files = list((destino / "payloads").glob("*.json"))
    assert len(payload_files) == 1
    recarregado = carrega_manifesto(destino / "manifest.json")
    assert recarregado == manifesto
    conteudo_payload = json.loads(payload_files[0].read_text(encoding="utf-8"))
    assert conteudo_payload["alert_id"] == str(selecionados[0][0].alert_id)


def test_carrega_manifesto_real_committed_e_hash_consistente_e_tem_a_forma_esperada():
    """`data/golden/v1/manifest.json` já é versionado no git (arquivo pequeno, não toca `core_sintetico.sqlite`),
    então esta verificação continua rápida/offline e segura para `pytest -k golden` (ADR-014)."""
    manifesto = carrega_manifesto(MANIFESTO_REAL)
    assert len(manifesto.alertas) == 500

    normais = sorted(
        contagem for rotulo, contagem in manifesto.contagem_por_estrato.items() if rotulo.startswith("Normal")
    )
    assert len(normais) == 11
    assert sum(normais) == 210

    suspeitas = sorted(
        (contagem for rotulo, contagem in manifesto.contagem_por_estrato.items() if not rotulo.startswith("Normal")),
        reverse=True,
    )
    assert suspeitas == sorted([30] * 6 + [10] * 11, reverse=True)


def test_carrega_manifesto_levanta_erro_se_manifest_sha256_adulterado(tmp_path):
    manifesto, selecionados = _manifesto_base()
    adulterado = manifesto.model_copy(update={"manifest_sha256": "0" * 64})
    destino = tmp_path / "adulterado_hash"
    grava_golden(destino, adulterado, selecionados)
    with pytest.raises(GoldenSetError, match="hash inconsistente"):
        carrega_manifesto(destino / "manifest.json")


def test_carrega_manifesto_levanta_erro_se_contagem_por_estrato_adulterada(tmp_path):
    manifesto, selecionados = _manifesto_base()
    adulterado = manifesto.model_copy(update={"contagem_por_estrato": {"Structuring": 999}})
    destino = tmp_path / "adulterado_contagem"
    grava_golden(destino, adulterado, selecionados)
    with pytest.raises(GoldenSetError, match="hash inconsistente"):
        carrega_manifesto(destino / "manifest.json")
