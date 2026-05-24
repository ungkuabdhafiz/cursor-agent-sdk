import json
from dataclasses import dataclass

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
class FakeRun:
    id: str = "run-1"

    def messages(self):
        yield AssistantMessage(
            type="assistant",
            message=AssistantPayload(content=[Block(type="text", text="hello")]),
        )


@dataclass
class FakeResult:
    status: str = "finished"
    model: object = None
    result: str = "done"
    duration_ms: int = 100


def test_stream_run_text(capsys) -> None:
    assert stream_run(FakeRun()) is True
    assert capsys.readouterr().out.strip() == "hello"


def test_json_result(capsys) -> None:
    print_run_summary(FakeResult(), streamed_text=True, json_mode=True, agent_id="a", run_id="r")
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["type"] == "result"
    assert payload["status"] == "finished"
    assert payload["agent_id"] == "a"
