def test_dispatcher_smoke(dispatcher) -> None:
    update_types = dispatcher.resolve_used_update_types()
    assert "message" in update_types
    assert "callback_query" in update_types
