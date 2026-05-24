import sys

from cursor_sdk import RunResult

from cursor_agent_sdk.model import format_model


def stream_run(run, *, show_tools: bool = True, show_meta: bool = False) -> bool:
    """Stream run messages to stdout. Returns True if assistant/thinking text was printed."""
    streamed_text = False
    seen_tool_calls: set[str] = set()

    if show_meta:
        print(f"Run ID: {run.id}", file=sys.stderr)

    for message in run.messages():
        if message.type == "assistant":
            for block in message.message.content:
                if getattr(block, "type", None) == "text" and block.text:
                    print(block.text, end="", flush=True)
                    streamed_text = True
        elif message.type == "thinking" and message.text:
            print(message.text, end="", flush=True)
            streamed_text = True
        elif message.type == "tool_call" and show_tools:
            if message.status != "running" or message.call_id in seen_tool_calls:
                continue
            seen_tool_calls.add(message.call_id)
            print(f"\n[tool] {message.name}", flush=True)
        elif message.type == "status" and message.message:
            print(f"\n[status] {message.status}: {message.message}", flush=True)
        elif message.type == "system" and message.model and show_meta:
            print(f"[system] model: {format_model(message.model)}\n", file=sys.stderr, flush=True)

    if streamed_text:
        print(flush=True)

    return streamed_text


def print_run_summary(result: RunResult, *, streamed_text: bool) -> None:
    print("\n--- Run complete ---", file=sys.stderr)
    print(f"Resolved model: {format_model(result.model)}", file=sys.stderr)
    print(f"Status: {result.status}", file=sys.stderr)
    if result.duration_ms:
        print(f"Duration: {result.duration_ms} ms", file=sys.stderr)

    if result.result and not streamed_text:
        print("\n--- Final result ---")
        print(result.result)
