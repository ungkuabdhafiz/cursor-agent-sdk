import os

from cursor_sdk import ModelParameterValue, ModelSelection


def use_fast_tier() -> bool:
    return os.environ.get("COMPOSER_FAST", "false").lower() in ("1", "true", "yes")


def build_model(*, fast: bool | None = None) -> ModelSelection:
    fast_tier = use_fast_tier() if fast is None else fast
    return ModelSelection(
        id="composer-2.5",
        params=[ModelParameterValue(id="fast", value="true" if fast_tier else "false")],
    )


def format_model(model) -> str:
    if model is None:
        return "unknown"

    model_id = getattr(model, "id", None) or str(model)
    params = getattr(model, "params", ()) or ()
    if not params:
        return model_id

    param_str = ", ".join(f"{param.id}={param.value}" for param in params)
    return f"{model_id} ({param_str})"
