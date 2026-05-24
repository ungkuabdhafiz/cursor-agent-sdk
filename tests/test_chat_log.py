import json
from dataclasses import dataclass, field

from cursor_agent_sdk.chat_log import (
    BufferedChatLogger,
    append_chat_log_event,
    log_user_prompt,
    serialize_sdk_message,
)
from cursor_agent_sdk.output import stream_run
from cursor_agent_sdk.session import chat_log_path


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
class ThinkingMessage:
    type: str
    text: str
    thinking_duration_ms: int | None = None


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
    id: str = "run-abc"

    def messages(self):
        for chunk in ("Let ", "me ", "check."):
            yield ThinkingMessage(type="thinking", text=chunk)
        yield ToolMessage(
            type="tool_call",
            call_id="c1",
            name="read",
            status="running",
            args={"path": "main.py"},
        )
        for chunk in ("Don", "e."):
            yield AssistantMessage(
                type="assistant",
                message=AssistantPayload(content=[Block(type="text", text=chunk)]),
            )


@dataclass
class FakeResult:
    status: str = "finished"
    model: object = None
    result: str = "Done."
    duration_ms: int = 50


def test_serialize_thinking_and_tool() -> None:
    thinking = serialize_sdk_message(
        ThinkingMessage(type="thinking", text="hmm"),
        run_id="r1",
        agent_id="a1",
    )
    assert thinking["message_type"] == "thinking"
    assert thinking["content"] == "hmm"

    tool = serialize_sdk_message(
        ToolMessage(
            type="tool_call",
            call_id="c1",
            name="grep",
            status="completed",
            args={"pattern": "foo"},
            result={"matches": 1},
        ),
        run_id="r1",
        agent_id="a1",
    )
    assert tool["tool"] == "grep"
    assert tool["args"] == {"pattern": "foo"}


def test_buffered_logger_merges_streaming_chunks(isolated_home, tmp_path) -> None:
    logger = BufferedChatLogger(tmp_path, run_id="run-1", agent_id="a1")
    for chunk in ("Let ", "me ", "check."):
        logger(ThinkingMessage(type="thinking", text=chunk))
    logger.flush()

    lines = [json.loads(line) for line in chat_log_path(tmp_path).read_text().splitlines()]
    assert len(lines) == 1
    assert lines[0]["message_type"] == "thinking"
    assert lines[0]["content"] == "Let me check."


def test_stream_run_logs_messages(isolated_home, tmp_path) -> None:
    logger = BufferedChatLogger(tmp_path, run_id="run-abc", agent_id="agent-1")
    stream_run(FakeRun(), log_message=logger)

    lines = [json.loads(line) for line in chat_log_path(tmp_path).read_text().splitlines()]
    types = [line["message_type"] for line in lines]
    assert types == ["thinking", "tool_call", "assistant"]
    assert lines[0]["content"] == "Let me check."
    assert lines[2]["content"] == "Done."


def test_chat_log_file(isolated_home, tmp_path) -> None:
    log_user_prompt(
        tmp_path,
        prompt="hello",
        run_id="run-1",
        agent_id="agent-1",
        mode="plan",
    )
    append_chat_log_event(
        tmp_path,
        serialize_sdk_message(
            ThinkingMessage(type="thinking", text="reasoning"),
            run_id="run-1",
            agent_id="agent-1",
        ),
    )

    lines = chat_log_path(tmp_path).read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    user = json.loads(lines[0])
    agent = json.loads(lines[1])
    assert user["role"] == "user"
    assert user["content"] == "hello"
    assert agent["message_type"] == "thinking"
    assert agent["content"] == "reasoning"
