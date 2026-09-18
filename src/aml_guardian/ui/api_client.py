"""Cliente REST da UI; a interface não acessa SQLite, Chroma ou Vault."""

from __future__ import annotations

from typing import Any

import httpx


class ApiClientError(RuntimeError):
    """Erro HTTP preservando apenas código e mensagem segura."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


class ApiClient:
    def __init__(self, base_url: str, token: str, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(base_url=base_url, timeout=10.0)
        self._headers = {"Authorization": f"Bearer {token}"}

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self._client.request(method, path, headers=self._headers, **kwargs)
        if response.is_error:
            try:
                message = str(response.json().get("detail", "erro HTTP"))
            except ValueError:
                message = "erro HTTP"
            raise ApiClientError(response.status_code, message)
        return response.json()

    def list_alerts(self, *, state: str | None = None, em_risco: bool | None = None) -> list[dict[str, Any]]:
        params = {key: value for key, value in {"state": state, "em_risco": em_risco}.items() if value is not None}
        return self._request("GET", "/alerts", params=params)

    def dossier(self, alert_id: str) -> dict[str, Any]:
        return self._request("GET", f"/dossiers/{alert_id}")

    def reidentify(self, alert_id: str) -> dict[str, Any]:
        return self._request("POST", f"/dossiers/{alert_id}/reidentify")

    def submit(self, alert_id: str) -> dict[str, Any]:
        return self._request("POST", f"/dossiers/{alert_id}/submit")

    def approve(self, alert_id: str, decision: str, justification: str) -> dict[str, Any]:
        return self._request(
            "POST", f"/dossiers/{alert_id}/approval", json={"decision": decision, "justification": justification}
        )
