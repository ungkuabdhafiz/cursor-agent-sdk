"""Composer model selection."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from cursor_sdk import ModelParameterValue, ModelSelection

from cursor_agent_sdk.config import DEFAULT_MODEL_ID, ToolConfig

if TYPE_CHECKING:
    from cursor_sdk.types import SDKModel


def use_fast_tier() -> bool:
    return os.environ.get("COMPOSER_FAST", "false").lower() in ("1", "true", "yes")


def resolve_fast(*, config: ToolConfig | None = None, fast: bool | None = None) -> bool:
    if fast is not None:
        return fast
    if config is not None and config.fast is not None:
        return config.fast
    return use_fast_tier()


def build_model(
    config: ToolConfig | None = None,
    *,
    fast: bool | None = None,
    model_id: str | None = None,
) -> ModelSelection:
    model = model_id or (config.model_id if config else None) or DEFAULT_MODEL_ID
    fast_tier = resolve_fast(config=config, fast=fast)
    return ModelSelection(
        id=model,
        params=[ModelParameterValue(id="fast", value="true" if fast_tier else "false")],
    )


def format_model(model: SDKModel | ModelSelection | None) -> str:
    if model is None:
        return "unknown"

    model_id = getattr(model, "id", None) or str(model)
    params = getattr(model, "params", ()) or ()
    if not params:
        return model_id

    param_str = ", ".join(f"{param.id}={param.value}" for param in params)
    return f"{model_id} ({param_str})"
