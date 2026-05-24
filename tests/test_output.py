import json
from dataclasses import dataclass, field

from cursor_agent_sdk.output import print_run_summary, stream_run


@dataclass
class Block:
    type: str
    text: str = ""


@dataclass
class AssistantPayload:
    content: list


@dataclass
class AssistantMessage:
    type: str
    message: AssistantPayload


@dataclass
class ToolMessage:
    type: str
    call_id: str
    name: str
    status: str
    args: dict = field(default_factory=dict)
    result: object = None


@dataclass
class FakeRun:
    id: str = "run-1"
    _messages: list = field(default_factory=list)

    def messages(self):
        yield from self._messages


def test_stream_run_tool_summary(capsys) -> None:
    run = FakeRun(
        _messages=[
            ToolMessage(
                type="tool_call",
                call_id="c1",
                name="grep",
                status="running",
                args={"pattern": "foo", "path": "src/"},
            ),
            ToolMessage(
                type="tool_call",
                call_id="c1",
                name="grep",
                status="completed",
                args={"pattern": "foo", "path": "src/"},
            ),
            AssistantMessage(
                type="assistant",
                message=AssistantPayload(content=[Block(type="text", text="done")]),
            ),
        ]
    )
    stream_run(run)
    out = capsys.readouterr().out
    assert "[tool] grep src/ pattern=foo" in out
    assert out.count("[tool]") == 1


@dataclass
class FakeResult:
    status: str = "finished"
    model: object = None
    result: str = "done"
    duration_ms: int = 100


def test_stream_run_text(capsys) -> None:
    run = FakeRun(
        _messages=[
            AssistantMessage(
                type="assistant",
                message=AssistantPayload(content=[Block(type="text", text="hello")]),
            ),
        ]
    )
    assert stream_run(run) is True
    assert capsys.readouterr().out.strip() == "hello"


def test_json_result(capsys) -> None:
    print_run_summary(FakeResult(), streamed_text=True, json_mode=True, agent_id="a", run_id="r")
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["type"] == "result"
    assert payload["status"] == "finished"
    assert payload["agent_id"] == "a"
