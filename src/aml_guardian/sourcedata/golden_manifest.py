"""Manifesto congelado por hash do golden set `v1` (T0.9, `SPEC.md` §8.3, ADR-014).

O manifesto (`data/golden/v1/manifest.json`) é versionado no git; os payloads DT-01 completos (dado pessoal
sintético) vão para `data/golden/v1/payloads/`, fora do git (`.gitignore`), regenerados deterministicamente
a partir do manifesto + seed + `core_sintetico`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from aml_guardian.contracts.ingestion import Alert
from aml_guardian.contracts.pipeline import Sha256Hex, VersionNumber


class GoldenSetError(ValueError):
    """Estrato sem candidatos suficientes para a quota, quota total acima da disponibilidade, ou manifesto
    carregado do disco com hash inconsistente com o próprio conteúdo (ADR-014)."""


class _ManifestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AlertaManifesto(_ManifestModel):
    alert_id: UUID
    estrato: str
    payload_sha256: Sha256Hex


class GoldenManifest(_ManifestModel):
    golden_version: str
    seed: int
    core_sintetico_sha256: Sha256Hex
    alert_rules_version: VersionNumber
    mapping_version: VersionNumber
    contagem_por_estrato: dict[str, int]
    disponibilidade_por_estrato: dict[str, int]
    alertas: list[AlertaManifesto]
    manifest_sha256: Sha256Hex


def payload_sha256(alerta: Alert) -> str:
    """SHA-256 do DT-01 canônico (`model_dump_json`: ordem de campo determinística pelo schema Pydantic)."""
    return hashlib.sha256(alerta.model_dump_json().encode("utf-8")).hexdigest()


def _conteudo_para_hash(
    *,
    golden_version: str,
    seed: int,
    core_sintetico_sha256: str,
    alert_rules_version: int,
    mapping_version: int,
    contagem_por_estrato: dict[str, int],
    disponibilidade_por_estrato: dict[str, int],
    alertas_ordenados: list[AlertaManifesto],
) -> bytes:
    corpo = {
        "golden_version": golden_version,
        "seed": seed,
        "core_sintetico_sha256": core_sintetico_sha256,
        "alert_rules_version": alert_rules_version,
        "mapping_version": mapping_version,
        "contagem_por_estrato": dict(sorted(contagem_por_estrato.items())),
        "disponibilidade_por_estrato": dict(sorted(disponibilidade_por_estrato.items())),
        "alertas": [item.model_dump(mode="json") for item in alertas_ordenados],
    }
    return json.dumps(corpo, sort_keys=True, ensure_ascii=False).encode("utf-8")


def _conteudo_para_hash_de_manifesto(manifesto: GoldenManifest) -> bytes:
    """Mesmo conteúdo de `_conteudo_para_hash`, mas lido dos campos de um `GoldenManifest` já construído —
    usado por `verifica_manifesto`, que só recebe o manifesto carregado do disco, nunca a seleção original."""
    return _conteudo_para_hash(
        golden_version=manifesto.golden_version,
        seed=manifesto.seed,
        core_sintetico_sha256=manifesto.core_sintetico_sha256,
        alert_rules_version=manifesto.alert_rules_version,
        mapping_version=manifesto.mapping_version,
        contagem_por_estrato=manifesto.contagem_por_estrato,
        disponibilidade_por_estrato=manifesto.disponibilidade_por_estrato,
        alertas_ordenados=manifesto.alertas,
    )


def constroi_manifesto(
    selecionados: list[tuple[Alert, str]],
    *,
    core_sintetico_sha256: str,
    alert_rules_version: int,
    mapping_version: int,
    seed: int,
    disponibilidade_por_estrato: dict[str, int],
    golden_version: str = "v1",
) -> GoldenManifest:
    """`selecionados`: pares (alerta, estrato) já amostrados. Ordena por `alert_id` (string) antes de tudo —
    nunca por ordem de geração — para o hash não depender de ordem de iteração acidental.
    `disponibilidade_por_estrato`: tamanho da pool golden de onde cada estrato foi amostrado (uma chave para
    cada rótulo de `contagem_por_estrato`), para permitir reponderação por probabilidade inversa de seleção."""
    ordenados = sorted(selecionados, key=lambda par: str(par[0].alert_id))
    alertas_manifesto = [
        AlertaManifesto(alert_id=alerta.alert_id, estrato=estrato, payload_sha256=payload_sha256(alerta))
        for alerta, estrato in ordenados
    ]
    contagem: dict[str, int] = {}
    for _, estrato in ordenados:
        contagem[estrato] = contagem.get(estrato, 0) + 1
    conteudo = _conteudo_para_hash(
        golden_version=golden_version,
        seed=seed,
        core_sintetico_sha256=core_sintetico_sha256,
        alert_rules_version=alert_rules_version,
        mapping_version=mapping_version,
        contagem_por_estrato=contagem,
        disponibilidade_por_estrato=disponibilidade_por_estrato,
        alertas_ordenados=alertas_manifesto,
    )
    return GoldenManifest(
        golden_version=golden_version,
        seed=seed,
        core_sintetico_sha256=core_sintetico_sha256,
        alert_rules_version=alert_rules_version,
        mapping_version=mapping_version,
        contagem_por_estrato=contagem,
        disponibilidade_por_estrato=disponibilidade_por_estrato,
        alertas=alertas_manifesto,
        manifest_sha256=hashlib.sha256(conteudo).hexdigest(),
    )


def grava_golden(destino: Path, manifesto: GoldenManifest, selecionados: list[tuple[Alert, str]]) -> None:
    """Grava `manifest.json` (versionado) e um payload DT-01 por alerta em `payloads/` (fora do git)."""
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "manifest.json").write_text(manifesto.model_dump_json(indent=2) + "\n", encoding="utf-8")
    payloads_dir = destino / "payloads"
    payloads_dir.mkdir(exist_ok=True)
    for alerta, _ in selecionados:
        arquivo = payloads_dir / f"{alerta.alert_id}.json"
        arquivo.write_text(alerta.model_dump_json(indent=2) + "\n", encoding="utf-8")


def verifica_manifesto(manifesto: GoldenManifest) -> None:
    """Recomputa `manifest_sha256` pelo mesmo método de `constroi_manifesto` e levanta `GoldenSetError` se não
    bater com o hash gravado — protege contra edição manual do `manifest.json` passar despercebida (ADR-014)."""
    esperado = hashlib.sha256(_conteudo_para_hash_de_manifesto(manifesto)).hexdigest()
    if esperado != manifesto.manifest_sha256:
        raise GoldenSetError(
            f"manifesto com hash inconsistente: esperado {esperado}, gravado {manifesto.manifest_sha256}"
        )


def carrega_manifesto(path: Path) -> GoldenManifest:
    manifesto = GoldenManifest.model_validate_json(path.read_text(encoding="utf-8"))
    verifica_manifesto(manifesto)
    return manifesto
