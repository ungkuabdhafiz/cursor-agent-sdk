from pathlib import Path

from cursor_agent_sdk.config import load_config, user_config_path


def test_load_home_config(isolated_home: Path, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    config_dir = user_config_path().parent
    config_dir.mkdir(parents=True)
    user_config_path().write_text(
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

