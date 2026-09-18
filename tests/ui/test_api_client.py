import httpx
import pytest

from aml_guardian.ui.api_client import ApiClient, ApiClientError
from aml_guardian.ui.session import select_alert


def _client(handler) -> ApiClient:
    transport = httpx.MockTransport(handler)
    return ApiClient("https://api.test", "token-ui", httpx.Client(transport=transport, base_url="https://api.test"))


def test_list_alerts_envia_filtros_e_bearer() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer token-ui"
        assert request.url.params["state"] == "DRAFT_READY"
        assert request.url.params["em_risco"] == "true"
        return httpx.Response(200, json=[{"alert_id": "a1"}])

    assert _client(handler).list_alerts(state="DRAFT_READY", em_risco=True) == [{"alert_id": "a1"}]


def test_erro_http_preserva_status_e_mensagem_segura() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"detail": {"code": "INVALID_STATE", "message": "estado inválido"}})

    with pytest.raises(ApiClientError) as error:
        _client(handler).submit("a1")

    assert error.value.status_code == 409
    assert "INVALID_STATE" in str(error.value)


def test_selecao_de_alerta_limpa_reidentificacao_anterior() -> None:
    state: dict[str, object] = {"selected_alert_id": "a1", "reidentified": {"CPF_01": "valor"}}

    select_alert(state, "a2")

    assert state == {"selected_alert_id": "a2"}
