from app.integrations.clash.client import ClashApiForbidden, ClashApiRateLimited, ClashApiUnavailable
from app.integrations.telegram.handlers.reports import _build_report_error_text


def test_report_error_text_for_forbidden() -> None:
    text = _build_report_error_text(ClashApiForbidden("403"), "en")
    assert "403" in text
    assert "IP" in text


def test_report_error_text_for_rate_limit() -> None:
    text = _build_report_error_text(ClashApiRateLimited("429"), "en")
    assert "429" in text


def test_report_error_text_for_unavailable() -> None:
    text = _build_report_error_text(ClashApiUnavailable("503"), "ru")
    assert "временно недоступен" in text
