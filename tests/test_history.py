import json
from types import SimpleNamespace

from cursor_agent_sdk.history import (
    _parse_agent_message,
    _parse_steps,
    _show_local_transcript,
)


def test_parse_agent_message_turn() -> None:
    message = SimpleNamespace(
        type="user",
        message={
            "turn": {
                "case": "agentConversationTurn",
                "value": {
                    "userMessage": {"text": "Hello"},
                    "steps": [
                        {
                            "message": {
                                "case": "thinkingMessage",
                                "value": {"text": "Thinking…"},
                            }
                        },
                        {
                            "message": {
                                "case": "assistantMessage",
                                "value": {"text": "Hi there."},
                            }
                        },
                        {
                            "message": {
                                "case": "toolCall",
                                "value": {
                                    "tool": {
                                        "case": "readToolCall",
                                        "value": {
                                            "args": {"path": "main.py"},
                                            "result": {"result": {"case": "success"}},
                                        },
                                    }
                                },
                            }
                        },
                    ],
                },
            }
        },
    )
    turn = _parse_agent_message(message, index=1)
    assert turn.user == "Hello"
    assert [s.kind for s in turn.steps] == ["thinking", "assistant", "tool"]
    assert turn.steps[2].tool == "read"
    assert turn.steps[2].args["path"] == "main.py"


def test_show_local_transcript(isolated_home, tmp_path, capsys) -> None:
    from cursor_agent_sdk.chat_log import log_user_prompt

    log_user_prompt(
        tmp_path,
        prompt="test",
        run_id="run-1",
        agent_id="a1",
        mode="plan",
    )
    code = _show_local_transcript(tmp_path, limit=None, json_mode=True)
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["source"] == "chat.jsonl"
    assert data["entries"][0]["content"] == "test"


def test_parse_steps_empty() -> None:
    assert _parse_steps([]) == []
