from pathlib import Path

from cursor_agent_sdk.config import ToolConfig, load_config, user_config_path
from cursor_agent_sdk.lean import apply_lean


def test_apply_lean_defaults() -> None:
    config = ToolConfig(
        setting_sources=("project", "user"),
        codegraph=__import__(
            "cursor_agent_sdk.codegraph", fromlist=["CodeGraphSettings"]
        ).CodeGraphSettings(enabled=True),
    )
    lean = apply_lean(config, rules_explicit=False, codegraph_explicit=False)
    assert lean.setting_sources == ("project",)
    assert lean.codegraph.enabled is False
    assert lean.default_mode == "plan"
    assert lean.lean is True


def test_apply_lean_respects_explicit_rules() -> None:
    config = ToolConfig(setting_sources=("project", "user"))
    lean = apply_lean(config, rules_explicit=True, codegraph_explicit=False)
    assert lean.setting_sources == ("project", "user")


def test_apply_lean_respects_explicit_codegraph() -> None:
    from cursor_agent_sdk.codegraph import CodeGraphSettings

    config = ToolConfig(codegraph=CodeGraphSettings(enabled=True))
    lean = apply_lean(config, rules_explicit=False, codegraph_explicit=True)
    assert lean.codegraph.enabled is True


def test_load_config_lean_default(isolated_home: Path, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    user_config_path().parent.mkdir(parents=True)
    user_config_path().write_text(
        """
[defaults]
lean = true
""",
        encoding="utf-8",
    )
    config = load_config(tmp_path)
    assert config.lean is True
