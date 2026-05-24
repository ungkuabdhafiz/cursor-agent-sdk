
from cursor_agent_sdk.config import ToolConfig
from cursor_agent_sdk.model import build_model, resolve_fast, use_fast_tier


def test_use_fast_tier_env(monkeypatch) -> None:
    monkeypatch.setenv("COMPOSER_FAST", "true")
    assert use_fast_tier() is True
    monkeypatch.setenv("COMPOSER_FAST", "0")
    assert use_fast_tier() is False


def test_build_model_standard() -> None:
    model = build_model(ToolConfig(model_id="composer-2.5", fast=False))
    assert model.id == "composer-2.5"
    assert model.params[0].id == "fast"
    assert model.params[0].value == "false"


def test_build_model_fast_flag() -> None:
    model = build_model(fast=True, model_id="composer-2.5")
    assert model.params[0].value == "true"


def test_resolve_fast_precedence() -> None:
    config = ToolConfig(fast=False)
    assert resolve_fast(config=config, fast=True) is True
    assert resolve_fast(config=config, fast=None) is False
