import pytest

from cursor_agent_sdk.completion import completion_script


def test_bash_completion() -> None:
    script = completion_script("bash")
    assert "cursor-agent-sdk" in script
    assert "plan" in script


def test_unsupported_shell() -> None:
    with pytest.raises(ValueError):
        completion_script("fish")
