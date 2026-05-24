from pathlib import Path

from cursor_agent_sdk.config import load_config


def test_load_project_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / ".cursor-agent"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        """
[defaults]
fast = true
session_name = "work"

[model]
id = "composer-2.5"

[local]
setting_sources = ["project", "user"]
sandbox_enabled = true
""",
        encoding="utf-8",
    )
    config = load_config(tmp_path)
    assert config.fast is True
    assert config.session_name == "work"
    assert config.setting_sources == ("project", "user")
    assert config.sandbox_enabled is True
