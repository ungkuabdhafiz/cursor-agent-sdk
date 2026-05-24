from cursor_agent_sdk.tool_display import format_tool_line, format_tool_summary


def test_read_shows_path() -> None:
    assert format_tool_summary("read", {"path": "/proj/src/main.py"}) == (
        "read /proj/src/main.py"
    )


def test_grep_shows_pattern() -> None:
    summary = format_tool_summary(
        "grep",
        {"pattern": "def main", "path": "/proj"},
    )
    assert summary == 'grep /proj pattern="def main"'


def test_shell_shows_command() -> None:
    summary = format_tool_summary("shell", {"command": "pytest -q"})
    assert summary == 'shell cmd="pytest -q"'


def test_edit_shows_path() -> None:
    summary = format_tool_summary(
        "edit",
        {"path": "cursor_agent_sdk/output.py", "old_string": "x", "new_string": "y"},
    )
    assert summary == "edit cursor_agent_sdk/output.py"


def test_tool_line_prefix() -> None:
    assert format_tool_line("glob", {"glob_pattern": "**/*.py"}) == (
        "[tool] glob pattern=**/*.py"
    )
