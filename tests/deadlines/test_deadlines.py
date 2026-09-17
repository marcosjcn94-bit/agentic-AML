"""Testes dos prazos do dossiê (T1.9, RF-09): +5 e +45 dias corridos com virada de mês/ano, e persistência DT-05."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from aml_guardian.contracts.ingestion import AlertState
from aml_guardian.deadlines.calculator import PRAZO_INTERNO_DIAS, PRAZO_REGULATORIO_DIAS, calculate_deadlines
from aml_guardian.deadlines.repository import get_deadlines, save_deadlines
from aml_guardian.persistence.db import init_db


class TestCalculateDeadlines:
    def test_mais_5_e_mais_45_dias_corridos(self):
        selecao_em = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)
        prazos = calculate_deadlines(selecao_em)
        assert prazos.prazo_interno == selecao_em + timedelta(days=PRAZO_INTERNO_DIAS)
        assert prazos.prazo_regulatorio_analise == selecao_em + timedelta(days=PRAZO_REGULATORIO_DIAS)

    def test_virada_de_mes_no_prazo_interno(self):
        selecao_em = datetime(2026, 9, 28, 10, 0, tzinfo=UTC)  # +5 dias cruza setembro -> outubro
        prazos = calculate_deadlines(selecao_em)
        assert prazos.prazo_interno == datetime(2026, 10, 3, 10, 0, tzinfo=UTC)

    def test_virada_de_mes_no_prazo_regulatorio(self):
        selecao_em = datetime(2026, 9, 17, 10, 0, tzinfo=UTC)  # +45 dias cruza setembro -> outubro -> novembro
        prazos = calculate_deadlines(selecao_em)
        assert prazos.prazo_regulatorio_analise == datetime(2026, 11, 1, 10, 0, tzinfo=UTC)

    def test_virada_de_ano(self):
        selecao_em = datetime(2026, 12, 30, 8, 0, tzinfo=UTC)
        prazos = calculate_deadlines(selecao_em)
        assert prazos.prazo_interno == datetime(2027, 1, 4, 8, 0, tzinfo=UTC)
        assert prazos.prazo_interno.year == 2027


class TestSaveAndGetDeadlines:
    @pytest.fixture
    def db_path(self, tmp_path: Path) -> Path:
        caminho = tmp_path / "test.sqlite"
        init_db(caminho)
        return caminho

    def test_persistencia_ida_e_volta(self, db_path: Path):
        alert_id = uuid4()
        selecao_em = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)
        prazos = calculate_deadlines(selecao_em)

        save_deadlines(alert_id, AlertState.TRIAGED, prazos, db_path=db_path)
        lidos = get_deadlines(alert_id, db_path=db_path)

        assert lidos == prazos

    def test_alerta_sem_registro_devolve_none(self, db_path: Path):
        assert get_deadlines(uuid4(), db_path=db_path) is None

    def test_upsert_atualiza_sem_duplicar(self, db_path: Path):
        alert_id = uuid4()
        selecao_em = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)
        prazos1 = calculate_deadlines(selecao_em)
        save_deadlines(alert_id, AlertState.TRIAGED, prazos1, db_path=db_path)

        prazos2 = calculate_deadlines(selecao_em + timedelta(days=1))
        save_deadlines(alert_id, AlertState.DRAFT_READY, prazos2, db_path=db_path)

        conn = sqlite3.connect(str(db_path))
        try:
            query = "SELECT COUNT(*) FROM alert_records WHERE alert_id = ?"
            count = conn.execute(query, (str(alert_id),)).fetchone()[0]
        finally:
            conn.close()

        assert count == 1
        assert get_deadlines(alert_id, db_path=db_path) == prazos2
