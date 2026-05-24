"""Fetch and display conversation history from the Cursor SDK agent store."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cursor_sdk import Agent, CursorClient, CursorAgentError

from cursor_agent_sdk.config import ToolConfig, build_agent_options, require_api_key
from cursor_agent_sdk.session import (
    chat_log_path,
    load_session,
    validate_session_cwd,
)


@dataclass
class HistoryStep:
    kind: str
    text: str = ""
    tool: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    status: str = ""


@dataclass
class HistoryTurn:
    index: int
    user: str
    steps: list[HistoryStep] = field(default_factory=list)
    run_id: str = ""


def show_history(
    cwd: Path,
    config: ToolConfig,
    *,
    agent_id: str | None = None,
    run_id: str | None = None,
    session_name: str = "default",
    limit: int | None = None,
    json_mode: bool = False,
    local_only: bool = False,
    full_tools: bool = False,
) -> int:
    if local_only:
        return _show_local_transcript(cwd, limit=limit, json_mode=json_mode)

    require_api_key()
    session = load_session(cwd, session_name)
    target_id = agent_id or (session.agent_id if session else None)
    if not target_id:
        print(
            "error: no agent to load. Run a plan/ask first, pass --agent-id, or use --local.",
            file=sys.stderr,
        )
        return 1

    if session is not None and agent_id is None:
        validate_session_cwd(session, cwd)

    client = CursorClient.launch_bridge(workspace=str(cwd))
    try:
        options = build_agent_options(cwd, config)
        agent = Agent.resume(target_id, options, client=client)
        try:
            if run_id:
                turns = _fetch_run_conversation(agent, run_id)
            else:
                turns = fetch_agent_turns(agent, limit=limit)
        finally:
            agent.close()
    finally:
        client.close()

    return _emit_turns(
        turns,
        agent_id=target_id,
        json_mode=json_mode,
        full_tools=full_tools,
        source="sdk",
    )


def fetch_agent_turns(agent: Agent, *, limit: int | None = None) -> list[HistoryTurn]:
    messages = agent.list_messages()
    turns = [_parse_agent_message(message, index=i + 1) for i, message in enumerate(messages)]
    if limit is not None and limit > 0:
        turns = turns[-limit:]
        for i, turn in enumerate(turns, start=1):
            turn.index = i
    return turns


def _fetch_run_conversation(agent: Agent, run_id: str) -> list[HistoryTurn]:
    run = agent.get_run(run_id)
    if not run.supports("conversation"):
        raise CursorAgentError(
            f"Run {run_id!r} does not support conversation export.",
            code="unsupported_operation",
        )
    turns: list[HistoryTurn] = []
    for index, item in enumerate(run.conversation(), start=1):
        turns.append(_parse_conversation_turn(item, index=index, run_id=run_id))
    return turns


def _parse_agent_message(message: Any, *, index: int) -> HistoryTurn:
    payload = message.message if isinstance(message.message, Mapping) else {}
    turn = _unwrap_turn(payload)
    user_text = _extract_user_text(turn)
    steps = _parse_steps(turn.get("steps") or ())
    return HistoryTurn(index=index, user=user_text, steps=steps)


def _parse_conversation_turn(item: Any, *, index: int, run_id: str) -> HistoryTurn:
    if item.type == "agentConversationTurn" and hasattr(item.turn, "user_message"):
        turn = {
            "userMessage": item.turn.user_message,
            "steps": [
                _step_to_dict(step)
                for step in getattr(item.turn, "steps", ())
            ],
        }
        return HistoryTurn(
            index=index,
            user=_extract_user_text(turn),
            steps=_parse_steps(turn.get("steps") or ()),
            run_id=run_id,
        )

    if item.type == "shellConversationTurn" and hasattr(item.turn, "shell_command"):
        cmd = item.turn.shell_command
        command = getattr(cmd, "command", "") if cmd else ""
        out = item.turn.shell_output
        stdout = getattr(out, "stdout", "") if out else ""
        return HistoryTurn(
            index=index,
            user="",
            steps=[
                HistoryStep(kind="shell", text=command, result=stdout),
            ],
            run_id=run_id,
        )

    return HistoryTurn(index=index, user="", steps=[HistoryStep(kind="unknown", text=str(item))])


def _step_to_dict(step: Any) -> dict[str, Any]:
    if isinstance(step, Mapping):
        return dict(step)
    step_type = getattr(step, "type", "")
    message = getattr(step, "message", None)
    if hasattr(message, "text"):
        return {"type": step_type, "message": {"text": message.text}}
    if isinstance(message, Mapping):
        return {"type": step_type, "message": dict(message)}
    return {"type": step_type, "message": message}


def _unwrap_turn(payload: Mapping[str, Any]) -> dict[str, Any]:
    turn = payload.get("turn")
    if isinstance(turn, Mapping):
        if "value" in turn and isinstance(turn["value"], Mapping):
            return dict(turn["value"])
        return dict(turn)
    return {}


def _extract_user_text(turn: Mapping[str, Any]) -> str:
    user = turn.get("userMessage")
    if isinstance(user, Mapping):
        return str(user.get("text") or "").strip()
    return ""


def _parse_steps(steps: Any) -> list[HistoryStep]:
    parsed: list[HistoryStep] = []
    if not isinstance(steps, (list, tuple)):
        return parsed

    for raw in steps:
        step = raw if isinstance(raw, Mapping) else _step_to_dict(raw)
        message = step.get("message")
        if not isinstance(message, Mapping):
            continue

        case = message.get("case") or step.get("type") or ""
        value = message.get("value")
        if not isinstance(value, Mapping):
            value = message

        if case in ("thinkingMessage", "thinking"):
            parsed.append(
                HistoryStep(kind="thinking", text=str(value.get("text") or ""))
            )
        elif case in ("assistantMessage", "assistant"):
            parsed.append(
                HistoryStep(kind="assistant", text=str(value.get("text") or ""))
            )
        elif case in ("toolCall", "tool_call"):
            parsed.append(_parse_tool_step(value))
        else:
            text = value.get("text") if isinstance(value, Mapping) else str(value)
            parsed.append(HistoryStep(kind=str(case or "step"), text=str(text)))
    return parsed


def _parse_tool_step(value: Mapping[str, Any]) -> HistoryStep:
    tool = value.get("tool")
    if isinstance(tool, Mapping):
        case = str(tool.get("case") or "")
        tool_value = tool.get("value")
        if not isinstance(tool_value, Mapping):
            tool_value = {}
        name = _tool_case_name(case)
        args = tool_value.get("args")
        if not isinstance(args, Mapping):
            args = {}
        result = tool_value.get("result")
        status = ""
        if isinstance(result, Mapping):
            status = str(result.get("result", {}).get("case", "")) if isinstance(
                result.get("result"), Mapping
            ) else ""
        return HistoryStep(
            kind="tool",
            tool=name,
            args=dict(args),
            result=result,
            status=status,
        )

    return HistoryStep(kind="tool", tool=str(value.get("name") or "tool"), args=dict(value))


def _tool_case_name(case: str) -> str:
    if case.endswith("ToolCall"):
        return case[: -len("ToolCall")]
    return case or "tool"


def _emit_turns(
    turns: list[HistoryTurn],
    *,
    agent_id: str,
    json_mode: bool,
    full_tools: bool,
    source: str,
) -> int:
    if not turns:
        print("No conversation history found.", file=sys.stderr)
        return 1

    if json_mode:
        payload = {
            "source": source,
            "agent_id": agent_id,
            "turns": [_turn_to_dict(turn) for turn in turns],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0

    print(f"Agent: {agent_id}  ({source})", file=sys.stderr)
    print(file=sys.stderr)
    for turn in turns:
        _print_turn(turn, full_tools=full_tools)
    return 0


def _print_turn(turn: HistoryTurn, *, full_tools: bool) -> None:
    header = f"--- Turn {turn.index}"
    if turn.run_id:
        header += f"  (run {turn.run_id})"
    header += " ---"
    print(header)
    print(f"user: {turn.user}\n")

    for step in turn.steps:
        if step.kind == "thinking" and step.text.strip():
            print(f"[thinking]\n{step.text.strip()}\n")
        elif step.kind == "assistant" and step.text.strip():
            print(f"[assistant]\n{step.text.strip()}\n")
        elif step.kind == "tool":
            summary = _format_tool_step(step, full=full_tools)
            print(f"[tool] {summary}\n")
        elif step.kind == "shell":
            print(f"[shell] {step.text}\n")
            if step.result:
                print(f"{step.result}\n")
        elif step.text.strip():
            print(f"[{step.kind}]\n{step.text.strip()}\n")


def _format_tool_step(step: HistoryStep, *, full: bool) -> str:
    parts = [step.tool or "tool"]
    if step.args:
        compact = _compact_args(step.args)
        if compact:
            parts.append(compact)
    if step.status:
        parts.append(f"status={step.status}")
    if step.result is not None:
        if full:
            parts.append(f"result={_truncate_repr(step.result, 2000)}")
        else:
            parts.append(f"result={_truncate_repr(step.result, 200)}")
    return " ".join(parts)


def _compact_args(args: Mapping[str, Any]) -> str:
    bits: list[str] = []
    for key in ("path", "pattern", "command", "query", "glob_pattern"):
        if key in args and args[key]:
            bits.append(f"{key}={_quote(str(args[key]))}")
    if bits:
        return " ".join(bits)
    encoded = json.dumps(dict(args), ensure_ascii=False, default=str)
    return _truncate_repr(encoded, 120)


def _quote(value: str) -> str:
    if " " in value:
        return json.dumps(value)
    return value


def _truncate_repr(value: Any, limit: int) -> str:
    text = repr(value) if not isinstance(value, str) else value
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _turn_to_dict(turn: HistoryTurn) -> dict[str, Any]:
    return {
        "index": turn.index,
        "run_id": turn.run_id,
        "user": turn.user,
        "steps": [
            {
                "kind": step.kind,
                "text": step.text,
                "tool": step.tool,
                "args": step.args,
                "result": step.result,
                "status": step.status,
            }
            for step in turn.steps
        ],
    }


def _show_local_transcript(
    cwd: Path,
    *,
    limit: int | None,
    json_mode: bool,
) -> int:
    path = chat_log_path(cwd)
    if not path.is_file():
        print(f"error: no local transcript at {path}", file=sys.stderr)
        return 1

    lines = path.read_text(encoding="utf-8").splitlines()
    if limit is not None and limit > 0:
        lines = lines[-limit:]

    entries = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    if json_mode:
        print(json.dumps({"source": "chat.jsonl", "path": str(path), "entries": entries}, indent=2))
        return 0

    print(f"Local transcript: {path}", file=sys.stderr)
    print(file=sys.stderr)
    for entry in entries:
        role = entry.get("role", "?")
        if role == "user":
            print(f"--- user ---\n{entry.get('content', entry.get('prompt', ''))}\n")
        elif role == "agent":
            kind = entry.get("message_type", "?")
            content = entry.get("content", "")
            if kind == "tool_call":
                tool = entry.get("tool", "?")
                print(f"[tool] {tool} {entry.get('args', entry.get('status', ''))}\n")
            elif content:
                print(f"[{kind}]\n{content}\n")
        elif role == "run":
            print(
                f"--- run {entry.get('status')} "
                f"({entry.get('model', '')}, {entry.get('duration_ms', '')} ms) ---\n"
            )
    return 0
