"""Streaming and JSON output for agent runs."""

from __future__ import annotations

import json
import sys
from typing import Any

from cursor_sdk import RunResult

from cursor_agent_sdk.model import format_model
from cursor_agent_sdk.tool_display import format_tool_line


def stream_run(
    run,
    *,
    show_tools: bool = True,
    show_meta: bool = False,
    json_mode: bool = False,
    verbose_tools: bool = False,
) -> bool:
    """Stream run messages. Returns True if assistant/thinking text was printed."""
    streamed_text = False
    seen_tool_calls: set[str] = set()

    if show_meta and not json_mode:
        print(f"Run ID: {run.id}", file=sys.stderr)

    for message in run.messages():
        if json_mode:
            _emit_json_event(message)
            if message.type in ("assistant", "thinking"):
                streamed_text = _message_has_text(message) or streamed_text
            continue

        if message.type == "assistant":
            for block in message.message.content:
                if getattr(block, "type", None) == "text" and block.text:
                    print(block.text, end="", flush=True)
                    streamed_text = True
        elif message.type == "thinking" and message.text:
            print(message.text, end="", flush=True)
            streamed_text = True
        elif message.type == "tool_call" and show_tools:
            streamed_text = _print_tool_call(
                message,
                seen_tool_calls,
                verbose=verbose_tools,
            ) or streamed_text
        elif message.type == "status" and message.message:
            print(f"\n[status] {message.status}: {message.message}", flush=True)
        elif message.type == "system" and message.model and show_meta:
            print(
                f"[system] model: {format_model(message.model)}\n",
                file=sys.stderr,
                flush=True,
            )

    if streamed_text and not json_mode:
        print(flush=True)

    return streamed_text


def print_run_summary(
    result: RunResult,
    *,
    streamed_text: bool,
    json_mode: bool = False,
    agent_id: str | None = None,
    run_id: str | None = None,
) -> None:
    if json_mode:
        payload: dict[str, Any] = {
            "type": "result",
            "status": result.status,
            "model": format_model(result.model),
            "result": result.result,
            "duration_ms": result.duration_ms,
            "agent_id": agent_id,
            "run_id": run_id,
        }
        print(json.dumps(payload, ensure_ascii=False))
        return

    print("\n--- Run complete ---", file=sys.stderr)
    print(f"Resolved model: {format_model(result.model)}", file=sys.stderr)
    print(f"Status: {result.status}", file=sys.stderr)
    if result.duration_ms:
        print(f"Duration: {result.duration_ms} ms", file=sys.stderr)

    if result.result and not streamed_text:
        print("\n--- Final result ---")
        print(result.result)


def _print_tool_call(message, seen: set[str], *, verbose: bool) -> bool:
    if verbose:
        if message.status == "running":
            if message.call_id in seen:
                return False
            seen.add(message.call_id)
            args_preview = _truncate(repr(message.args), 200)
            print(
                f"\n[tool] {message.name} ({message.status}) args={args_preview}",
                flush=True,
            )
        elif message.status in ("completed", "error") and message.result is not None:
            result_preview = _truncate(repr(message.result), 200)
            print(f"[tool] {message.name} result={result_preview}", flush=True)
        return False

    if message.call_id in seen or message.status != "running":
        return False
    seen.add(message.call_id)
    line = format_tool_line(message.name, message.args, status=message.status)
    print(f"\n{line}", flush=True)
    return False


def _emit_json_event(message) -> None:
    event: dict[str, Any] = {"type": message.type}
    if message.type == "assistant":
        texts = []
        for block in message.message.content:
            if getattr(block, "type", None) == "text" and block.text:
                texts.append(block.text)
        event["text"] = "".join(texts)
    elif message.type == "thinking":
        event["text"] = message.text
    elif message.type == "tool_call":
        event.update(
            {
                "name": message.name,
                "call_id": message.call_id,
                "status": message.status,
                "args": message.args,
                "result": message.result,
            }
        )
    elif message.type == "status":
        event.update({"status": message.status, "message": message.message})
    print(json.dumps(event, ensure_ascii=False, default=str))


def _message_has_text(message) -> bool:
    if message.type == "thinking":
        return bool(message.text)
    if message.type == "assistant":
        for block in message.message.content:
            if getattr(block, "type", None) == "text" and block.text:
                return True
    return False


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."
