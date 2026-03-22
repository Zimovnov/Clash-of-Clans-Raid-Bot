import pytest

from app.core.config import get_settings
from app.integrations.clash.client import ClashApiClient, ClashApiError, ClashApiUnavailable


class _FakeResponse:
    def __init__(self, *, status_code: int, text: str = "", payload: dict | None = None) -> None:
        self.status_code = status_code
        self.text = text
        self._payload = payload or {}

    def json(self) -> dict:
        return self._payload


class _FakeAsyncClient:
    def __init__(self, response: _FakeResponse | None = None, exception: Exception | None = None, **kwargs) -> None:
        self.response = response
        self.exception = exception

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def request(self, method: str, url: str, headers: dict[str, str]):
        if self.exception is not None:
            raise self.exception
        if self.response is None:
            raise RuntimeError("Fake response is not configured")
        return self.response


@pytest.mark.asyncio
async def test_clash_api_error_hides_response_body(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.integrations.clash.client.httpx.AsyncClient",
        lambda **kwargs: _FakeAsyncClient(response=_FakeResponse(status_code=400, text="secret-response-body")),
    )
    get_settings.cache_clear()

    with pytest.raises(ClashApiError) as exc_info:
        await ClashApiClient().get_clan("#ABC")

    assert "400" in str(exc_info.value)
    assert "secret-response-body" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_clash_api_timeout_becomes_unavailable(monkeypatch) -> None:
    import httpx

    monkeypatch.setattr(
        "app.integrations.clash.client.httpx.AsyncClient",
        lambda **kwargs: _FakeAsyncClient(exception=httpx.TimeoutException("boom")),
    )
    get_settings.cache_clear()

    with pytest.raises(ClashApiUnavailable) as exc_info:
        await ClashApiClient().get_clan("#ABC")

    assert "timed out" in str(exc_info.value)
