import argparse
import sys
from pathlib import Path

from cursor_sdk import CursorAgentError

from cursor_agent_sdk.model import use_fast_tier
from cursor_agent_sdk.session import load_session
from cursor_agent_sdk.tool import AgentTool, clear_project_session, run_chat


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cursor-agent-sdk",
        description=(
            "Delegate coding tasks to a Cursor SDK agent for the current project. "
            "Use plan mode to get suggestions, then send follow-ups to implement them."
        ),
    )
    parser.add_argument(
        "--cwd",
        type=Path,
        default=Path.cwd(),
        help="Project directory the SDK agent should work in (default: current directory)",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Use Composer fast tier (default: standard tier via fast=false)",
    )
    parser.add_argument(
        "--no-tools",
        action="store_true",
        help="Hide tool call lines in output",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print agent and run metadata on stderr",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser(
        "plan",
        help="Start or continue a session in plan mode and ask for a proposal",
    )
    plan.add_argument("prompt", help="What you want to build or change")

    ask = subparsers.add_parser(
        "ask",
        help="Start or continue a session in agent mode and execute a task",
    )
    ask.add_argument("prompt", help="What you want the agent to do")

    send = subparsers.add_parser(
        "send",
        help="Send a follow-up message in the saved session for this project",
    )
    send.add_argument("prompt", help="Follow-up instruction for the existing session")
    send.add_argument(
        "--mode",
        choices=("plan", "agent"),
        help="Override conversation mode for this message",
    )

    chat = subparsers.add_parser(
        "chat",
        help="Open an interactive multi-turn session",
    )
    chat.add_argument(
        "--start-mode",
        choices=("plan", "agent"),
        default="plan",
        help="Initial mode for a new chat session (default: plan)",
    )

    resume = subparsers.add_parser(
        "resume",
        help="Resume a specific agent ID and optionally send a prompt",
    )
    resume.add_argument("agent_id", help="Existing local agent ID")
    resume.add_argument("prompt", nargs="?", help="Optional prompt to send immediately")

    session = subparsers.add_parser(
        "session",
        help="Show the saved session for this project",
    )

    clear = subparsers.add_parser(
        "clear",
        help="Delete the saved session file for this project",
    )

    for subparser in (plan, ask):
        subparser.add_argument(
            "--new",
            action="store_true",
            help="Force a new SDK session instead of continuing the saved one",
        )

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    cwd = args.cwd.resolve()
    if not cwd.is_dir():
        print(f"error: --cwd is not a directory: {cwd}", file=sys.stderr)
        raise SystemExit(1)

    fast = True if args.fast else use_fast_tier()
    show_tools = not args.no_tools
    show_meta = args.verbose

    try:
        if args.command == "chat":
            code = run_chat(
                cwd,
                fast=fast,
                show_tools=show_tools,
                show_meta=show_meta,
                initial_mode=args.start_mode,
            )
            raise SystemExit(code)

        if args.command == "session":
            session = load_session(cwd)
            if session is None:
                print("No saved session for this project.", file=sys.stderr)
                raise SystemExit(1)
            print(f"Agent ID: {session.agent_id}")
            print(f"Project: {session.cwd}")
            print(f"Created: {session.created_at}")
            print(f"Updated: {session.updated_at}")
            print(f"Last mode: {session.last_mode}")
            raise SystemExit(0)

        if args.command == "clear":
            raise SystemExit(clear_project_session(cwd))

        with AgentTool(cwd, fast=fast, show_tools=show_tools, show_meta=show_meta) as tool:
            if args.command == "plan":
                if args.new:
                    tool.open_new(mode="plan")
                else:
                    session = load_session(cwd)
                    if session is None:
                        tool.open_new(mode="plan")
                    else:
                        tool.open_existing(session.agent_id)
                raise SystemExit(tool.send(args.prompt, mode="plan"))

            if args.command == "ask":
                if args.new:
                    tool.open_new(mode="agent")
                else:
                    session = load_session(cwd)
                    if session is None:
                        tool.open_new(mode="agent")
                    else:
                        tool.open_existing(session.agent_id)
                raise SystemExit(tool.send(args.prompt, mode="agent"))

            if args.command == "send":
                tool.open_existing()
                raise SystemExit(tool.send(args.prompt, mode=args.mode))

            if args.command == "resume":
                tool.open_existing(args.agent_id)
                if args.prompt:
                    raise SystemExit(tool.send(args.prompt))
                print(
                    f"Resumed {args.agent_id}. Use `cursor-agent-sdk send` for follow-ups.",
                    file=sys.stderr,
                )
                raise SystemExit(0)

    except CursorAgentError as err:
        print(f"error: {err.message}", file=sys.stderr)
        if err.is_retryable:
            print("This error may be retryable.", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
