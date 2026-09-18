"""Fluxo RF-12/RF-13 pelo navegador, com API REST sintética e sem persistência."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from playwright.sync_api import Page

PII_CANARY = "CPF-CANARIO-52998224725"
ALERT_ID = "11111111-1111-4111-8111-111111111111"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class _ApiHandler(BaseHTTPRequestHandler):
    state = "DRAFT_READY"
    approval_received = False

    def log_message(self, _format: str, *args: Any) -> None:
        return

    def _json(self, status: int, body: Any, **headers: str) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        for name, value in headers.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/alerts"):
            self._json(200, [{"alert_id": ALERT_ID, "state": self.state, "em_risco": False}])
            return
        if self.path == f"/dossiers/{ALERT_ID}":
            self._json(
                200,
                {
                    "dossier_id": "dossie-e2e",
                    "type": "COS",
                    "ai_generated_fields": ["typology_hypothesis"],
                    "citations": [{"article_ref": "CC4001/art1/i1/d"}],
                },
            )
            return
        self._json(404, {"detail": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path == f"/dossiers/{ALERT_ID}/reidentify":
            self._json(200, {"tokens": {"CPF_01": PII_CANARY}}, **{"Cache-Control": "no-store"})
            return
        if self.path == f"/dossiers/{ALERT_ID}/submit":
            type(self).state = "SUBMITTED"
            self._json(200, {"alert_id": ALERT_ID, "state": self.state})
            return
        if self.path == f"/dossiers/{ALERT_ID}/approval":
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length))
            assert len(body["justification"].strip()) >= 50
            type(self).approval_received = True
            type(self).state = "APPROVED"
            self._json(200, {"alert_id": ALERT_ID, "state": self.state})
            return
        self._json(404, {"detail": "not found"})


def _wait_for(url: str, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1):  # noqa: S310 - loopback de teste
                return
        except OSError:
            time.sleep(0.2)
    raise TimeoutError(f"serviço não iniciou: {url}")


def test_fluxo_humano_completo_no_navegador(page: Page) -> None:
    _ApiHandler.state = "DRAFT_READY"
    _ApiHandler.approval_received = False
    api = ThreadingHTTPServer(("127.0.0.1", 0), _ApiHandler)
    api_thread = threading.Thread(target=api.serve_forever, daemon=True)
    api_thread.start()

    ui_port = _free_port()
    root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env.update(
        {
            "AML_API_URL": f"http://127.0.0.1:{api.server_port}",
            "API_TOKEN_ANALISTA": "token-e2e-analista",
            "API_TOKEN_COMPLIANCE_OFFICER": "token-e2e-officer",
        }
    )
    process = subprocess.Popen(  # noqa: S603
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "src/aml_guardian/ui/app.py",
            "--server.headless=true",
            f"--server.port={ui_port}",
            "--browser.gatherUsageStats=false",
        ],
        cwd=root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    output = ""
    try:
        _wait_for(f"http://127.0.0.1:{ui_port}/_stcore/health")
        page.goto(f"http://127.0.0.1:{ui_port}")
        page.get_by_text("Dossiê mascarado").wait_for()

        page.get_by_role("button", name="Reidentificar").click()
        page.get_by_text(PII_CANARY).wait_for()
        page.get_by_role("button", name="Submeter para decisão").click()
        page.get_by_text("Dossiê submetido.").wait_for()

        page.reload()
        justification = page.get_by_role("textbox", name="Justificativa")
        justification.wait_for()
        justification.fill(
            "Decisão humana fundamentada nas evidências e citações verificadas do dossiê."
        )
        page.get_by_role("button", name="Registrar decisão").click()
        page.get_by_text("Decisão registrada.").wait_for()
        assert _ApiHandler.approval_received
    finally:
        process.terminate()
        try:
            output, _ = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            output, _ = process.communicate(timeout=5)
        api.shutdown()
        api.server_close()

    assert PII_CANARY not in output
    assert "token-e2e" not in output
