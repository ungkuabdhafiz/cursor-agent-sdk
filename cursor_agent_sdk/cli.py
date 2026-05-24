"""Command-line interface for cursor-agent-sdk."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cursor_sdk import CursorAgentError

from cursor_agent_sdk.completion import completion_script
from cursor_agent_sdk.config import ToolConfig, load_config
from cursor_agent_sdk.errors import format_error, format_error_hint
from cursor_agent_sdk.session import SessionCwdMismatchError, load_session
from cursor_agent_sdk.tool import (
    AgentTool,
    clear_project_session,
    list_project_sessions,
    read_prompt_arg,
    run_chat,
)


def global_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--cwd",
        type=Path,
        default=Path.cwd(),
        help="Project directory the SDK agent should work in (default: current directory)",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        default=None,
        help="Use Composer fast tier",
    )
    parser.add_argument(
        "--no-fast",
        action="store_true",
        help="Force standard tier (overrides COMPOSER_FAST)",
    )
    parser.add_argument(
        "--model",
        metavar="ID",
        help="Model id (default: composer-2.5, or CURSOR_AGENT_MODEL / config)",
    )
    parser.add_argument(
        "--session",
        metavar="NAME",
        help="Named session (stored under .cursor-agent-sdk/sessions/)",
    )
    parser.add_argument(
        "--rules",
        nargs="+",
        metavar="SOURCE",
        help="Setting sources: project, user, team, mdm, plugins, all",
    )
    parser.add_argument(
        "--sandbox",
        action="store_true",
        default=None,
        help="Enable sandbox for local agent",
    )
    parser.add_argument(
        "--no-sandbox",
        action="store_true",
        help="Disable sandbox",
    )
    parser.add_argument(
        "--no-tools",
        action="store_true",
        help="Hide tool call lines in output",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print agent/run metadata and verbose tool details on stderr",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit NDJSON events during the run and a final JSON result",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cursor-agent-sdk",
        description=(
            "Delegate coding tasks to a Cursor SDK agent for the current project. "
            "Use plan mode to get suggestions, then send follow-ups to implement them."
        ),
    )
    global_arguments(parser)

    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("plan", help="Start or continue a session in plan mode")
    plan.add_argument("prompt", help='Task description, or "-" to read from stdin')
    global_arguments(plan)

    ask = subparsers.add_parser("ask", help="Start or continue a session in agent mode")
    ask.add_argument("prompt", help='Task description, or "-" to read from stdin')
    global_arguments(ask)

    send = subparsers.add_parser("send", help="Send a follow-up in the saved session")
    send.add_argument("prompt", help='Follow-up instruction, or "-" for stdin')
    send.add_argument(
        "--mode",
        choices=("plan", "agent"),
        help="Override conversation mode for this message",
    )
    global_arguments(send)

    chat = subparsers.add_parser("chat", help="Open an interactive multi-turn session")
    chat.add_argument(
        "--start-mode",
        choices=("plan", "agent"),
        default=None,
        help="Initial mode for a new chat session",
    )
    chat.add_argument(
        "--new",
        action="store_true",
        help="Force a new SDK session instead of resuming",
    )
    global_arguments(chat)

    resume = subparsers.add_parser(
        "resume",
        help="Resume a specific agent ID and optionally send a prompt",
    )
    resume.add_argument("agent_id", help="Existing local agent ID")
    resume.add_argument("prompt", nargs="?", help='Optional prompt, or "-" for stdin')
    global_arguments(resume)

    session_cmd = subparsers.add_parser("session", help="Show the saved session for this project")
    global_arguments(session_cmd)

    sessions_cmd = subparsers.add_parser("sessions", help="List named sessions for this project")
    global_arguments(sessions_cmd)

    clear = subparsers.add_parser("clear", help="Delete the saved session file for this project")
    global_arguments(clear)

    completion = subparsers.add_parser("completion", help="Print shell completion script")
    completion.add_argument("shell", choices=("bash", "zsh"), help="Shell type")

    for subparser in (plan, ask):
        subparser.add_argument(
            "--new",
            action="store_true",
            help="Force a new SDK session instead of continuing the saved one",
        )

    return parser


def resolve_config(args: argparse.Namespace, cwd: Path) -> ToolConfig:
    config = load_config(cwd)

    fast = args.fast
    if getattr(args, "no_fast", False):
        fast = False

    sandbox = config.sandbox_enabled
    if getattr(args, "sandbox", None):
        sandbox = True
    if getattr(args, "no_sandbox", False):
        sandbox = False

    show_tools = None if not args.no_tools else False
    show_meta = True if args.verbose else None

    return config.merge_cli(
        model_id=args.model,
        fast=fast,
        show_tools=show_tools,
        show_meta=show_meta,
        session_name=args.session,
        rules=args.rules,
        sandbox=sandbox,
    )


def resolve_fast_flag(args: argparse.Namespace, config: ToolConfig) -> bool | None:
    if getattr(args, "no_fast", False):
        return False
    if args.fast:
        return True
    return config.fast


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "completion":
        print(completion_script(args.shell))
        raise SystemExit(0)

    cwd = args.cwd.resolve()
    if not cwd.is_dir():
        print(f"error: --cwd is not a directory: {cwd}", file=sys.stderr)
        raise SystemExit(1)

    config = resolve_config(args, cwd)
    fast = resolve_fast_flag(args, config)
    json_mode = bool(args.json)
    session_name = config.session_name

    try:
        if args.command == "chat":
            start_mode = args.start_mode or config.default_mode
            code = run_chat(
                cwd,
                config,
                fast=fast,
                show_tools=config.show_tools,
                show_meta=config.show_meta,
                json_mode=json_mode,
                initial_mode=start_mode,  # type: ignore[arg-type]
                force_new=args.new,
                session_name=session_name,
            )
            raise SystemExit(code)

        if args.command == "session":
            session = load_session(cwd, session_name)
            if session is None:
                print("No saved session for this project.", file=sys.stderr)
                raise SystemExit(1)
            print(f"Agent ID: {session.agent_id}")
            print(f"Project: {session.cwd}")
            print(f"Session: {session.session_name}")
            print(f"Version: {session.version}")
            print(f"Created: {session.created_at}")
            print(f"Updated: {session.updated_at}")
            print(f"Last mode: {session.last_mode}")
            raise SystemExit(0)

        if args.command == "sessions":
            names = list_project_sessions(cwd)
            if not names:
                print("No saved sessions.", file=sys.stderr)
                raise SystemExit(1)
            for name in names:
                print(name)
            raise SystemExit(0)

        if args.command == "clear":
            raise SystemExit(clear_project_session(cwd, session_name))

        with AgentTool(
            cwd,
            config,
            fast=fast,
            show_tools=config.show_tools,
            show_meta=config.show_meta,
            json_mode=json_mode,
            session_name=session_name,
        ) as tool:
            if args.command == "plan":
                prompt = read_prompt_arg(args.prompt)
                if args.new:
                    tool.open_new(mode="plan")
                else:
                    session = load_session(cwd, session_name)
                    if session is None:
                        tool.open_new(mode="plan")
                    else:
                        validate_and_open(tool, session)
                raise SystemExit(tool.send(prompt, mode="plan"))

            if args.command == "ask":
                prompt = read_prompt_arg(args.prompt)
                if args.new:
                    tool.open_new(mode="agent")
                else:
                    session = load_session(cwd, session_name)
                    if session is None:
                        tool.open_new(mode="agent")
                    else:
                        validate_and_open(tool, session)
                raise SystemExit(tool.send(prompt, mode="agent"))

            if args.command == "send":
                prompt = read_prompt_arg(args.prompt)
                tool.open_existing()
                raise SystemExit(tool.send(prompt, mode=args.mode))

            if args.command == "resume":
                tool.open_existing(args.agent_id)
                if args.prompt:
                    prompt = read_prompt_arg(args.prompt)
                    raise SystemExit(tool.send(prompt))
                print(
                    f"Resumed {args.agent_id}. Use `cursor-agent-sdk send` for follow-ups.",
                    file=sys.stderr,
                )
                raise SystemExit(0)

    except (CursorAgentError, SessionCwdMismatchError, ValueError) as err:
        print(f"error: {format_error(err)}", file=sys.stderr)
        hint = format_error_hint(err)
        if hint:
            print(hint, file=sys.stderr)
        if isinstance(err, CursorAgentError) and err.is_retryable:
            print("This error may be retryable.", file=sys.stderr)
        raise SystemExit(1)


def validate_and_open(tool: AgentTool, session) -> None:
    from cursor_agent_sdk.session import validate_session_cwd

    validate_session_cwd(session, tool.cwd)
    tool.open_existing(session.agent_id)


if __name__ == "__main__":
    main()
