from app.integrations.telegram.router import build_dispatcher


def test_dispatcher_smoke() -> None:
    dp = build_dispatcher()
    update_types = dp.resolve_used_update_types()
    assert "message" in update_types
    assert "callback_query" in update_types
