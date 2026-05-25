"""Command-line interface for cursor-agent-sdk."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cursor_sdk import CursorAgentError

from cursor_agent_sdk import __version__
from cursor_agent_sdk.codegraph import inspect_status, run_init
from cursor_agent_sdk.completion import completion_script
from cursor_agent_sdk.config import ToolConfig, load_config, require_api_key
from cursor_agent_sdk.lean import apply_lean, emit_lean_banner, warn_lean_session_resume
from cursor_agent_sdk.errors import format_error, format_error_hint, print_error_details
from cursor_agent_sdk.session import (
    SessionCwdMismatchError,
    home_dir,
    list_projects,
    load_session,
    project_store_dir,
)
from cursor_agent_sdk.history import show_history
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
        default=None,
        help="Project directory (default: your current working directory)",
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
        help="Named session (under ~/.cursor-agent-sdk/projects/<id>/sessions/)",
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
        help=(
            "Print agent/run metadata, verbose tool details, and extra "
            "SDK error fields on stderr"
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit NDJSON events during the run and a final JSON result",
    )
    parser.add_argument(
        "--lean",
        action="store_true",
        help=(
            "Token-efficient defaults: project rules only, CodeGraph MCP off, "
            "plan-first; warns when resuming long sessions"
        ),
    )
    codegraph_group = parser.add_mutually_exclusive_group()
    codegraph_group.add_argument(
        "--codegraph",
        action="store_true",
        default=None,
        help="Enable CodeGraph MCP for the target project (default)",
    )
    codegraph_group.add_argument(
        "--no-codegraph",
        action="store_true",
        help="Disable automatic CodeGraph MCP injection",
    )


_GLOBAL_PARSER = argparse.ArgumentParser(add_help=False)
global_arguments(_GLOBAL_PARSER)


def parse_cli_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse argv; global flags may appear before or after the subcommand."""
    global_ns, remaining = _GLOBAL_PARSER.parse_known_args(argv)
    args = build_parser().parse_args(remaining)
    return _merge_global_args(args, global_ns)


def _merge_global_args(
    command_ns: argparse.Namespace,
    global_ns: argparse.Namespace,
) -> argparse.Namespace:
    for key, value in vars(global_ns).items():
        setattr(command_ns, key, value)
    return command_ns


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cursor-agent-sdk",
        description=(
            "Delegate coding tasks to a Cursor SDK agent for the current project. "
            "Use plan mode to get suggestions, then send follow-ups to implement them."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("plan", help="Start or continue a session in plan mode")
    plan.add_argument("prompt", help='Task description, or "-" to read from stdin')

    ask = subparsers.add_parser("ask", help="Start or continue a session in agent mode")
    ask.add_argument("prompt", help='Task description, or "-" to read from stdin')

    send = subparsers.add_parser("send", help="Send a follow-up in the saved session")
    send.add_argument("prompt", help='Follow-up instruction, or "-" for stdin')
    send.add_argument(
        "--mode",
        choices=("plan", "agent"),
        help="Override conversation mode for this message",
    )

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

    resume = subparsers.add_parser(
        "resume",
        help="Resume a specific agent ID and optionally send a prompt",
    )
    resume.add_argument("agent_id", help="Existing local agent ID")
    resume.add_argument("prompt", nargs="?", help='Optional prompt, or "-" for stdin')

    session_cmd = subparsers.add_parser("session", help="Show the saved session for this project")

    sessions_cmd = subparsers.add_parser("sessions", help="List named sessions for this project")

    projects_cmd = subparsers.add_parser(
        "projects",
        help="List all projects with saved sessions under ~/.cursor-agent-sdk",
    )

    clear = subparsers.add_parser("clear", help="Delete the saved session file for this project")

    history_cmd = subparsers.add_parser(
        "history",
        help="Show conversation history from the SDK agent store (or --local transcript)",
    )
    history_cmd.add_argument(
        "--agent-id",
        metavar="ID",
        help="Agent ID to load (default: saved session for this project)",
    )
    history_cmd.add_argument(
        "--run",
        metavar="RUN_ID",
        help="Show conversation for a single run instead of the full agent session",
    )
    history_cmd.add_argument(
        "--limit",
        type=int,
        metavar="N",
        help="Show only the last N turns or transcript lines",
    )
    history_cmd.add_argument(
        "--local",
        action="store_true",
        help="Show chat.jsonl transcript only (no API / bridge required)",
    )
    history_cmd.add_argument(
        "--full",
        action="store_true",
        help="Include full tool results in text output",
    )
    codegraph_cmd = subparsers.add_parser("codegraph", help="CodeGraph index utilities")
    codegraph_sub = codegraph_cmd.add_subparsers(dest="codegraph_command", required=True)
    codegraph_status = codegraph_sub.add_parser(
        "status",
        help="Show CodeGraph binary and index status for --cwd",
    )
    codegraph_init = codegraph_sub.add_parser(
        "init",
        help="Run codegraph init -i in the target project",
    )

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

    codegraph = None
    if getattr(args, "no_codegraph", False):
        codegraph = False
    elif getattr(args, "codegraph", None):
        codegraph = True

    merged = config.merge_cli(
        model_id=args.model,
        fast=fast,
        show_tools=show_tools,
        show_meta=show_meta,
        session_name=args.session,
        rules=args.rules,
        sandbox=sandbox,
        codegraph=codegraph,
        lean=True if getattr(args, "lean", False) else None,
    )

    use_lean = bool(getattr(args, "lean", False)) or merged.lean
    if not use_lean:
        return merged

    codegraph_explicit = bool(
        getattr(args, "no_codegraph", False) or getattr(args, "codegraph", False)
    )
    return apply_lean(
        merged,
        rules_explicit=args.rules is not None,
        codegraph_explicit=codegraph_explicit,
    )


def resolve_fast_flag(args: argparse.Namespace, config: ToolConfig) -> bool | None:
    if getattr(args, "no_fast", False):
        return False
    if args.fast:
        return True
    return config.fast


def main(argv: list[str] | None = None) -> None:
    args = parse_cli_args(argv)

    if args.command == "completion":
        print(completion_script(args.shell))
        raise SystemExit(0)

    cwd = (args.cwd or Path.cwd()).resolve()
    if not cwd.is_dir():
        print(f"error: --cwd is not a directory: {cwd}", file=sys.stderr)
        raise SystemExit(1)

    if args.command == "codegraph":
        config = resolve_config(args, cwd)
        if args.codegraph_command == "status":
            status = inspect_status(cwd, config.codegraph)
            print(f"Project: {status.project}")
            print(f"Enabled: {status.enabled}")
            print(f"Binary: {status.command or 'not found'}")
            print(f"Index: {'initialized' if status.index_initialized else 'missing'}")
            raise SystemExit(0 if status.command else 1)
        if args.codegraph_command == "init":
            raise SystemExit(run_init(cwd, config.codegraph))
        raise SystemExit(1)

    needs_api_key = args.command != "projects" and not (
        args.command == "history" and getattr(args, "local", False)
    )
    if needs_api_key:
        try:
            require_api_key()
        except RuntimeError as err:
            print(f"error: {err}", file=sys.stderr)
            raise SystemExit(1)

    config = resolve_config(args, cwd)
    fast = resolve_fast_flag(args, config)
    json_mode = bool(args.json)
    session_name = config.session_name

    if config.lean and not json_mode and args.command not in (
        "projects",
        "sessions",
        "session",
        "history",
        "clear",
        "completion",
    ):
        emit_lean_banner(config)

    try:
        if args.command == "chat":
            warn_lean_session_resume(
                cwd,
                session_name,
                lean=config.lean,
                force_new=args.new,
            )
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
            print(f"Store: {project_store_dir(cwd)}")
            print(f"Home: {home_dir()}")
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

        if args.command == "projects":
            entries = list_projects()
            if not entries:
                print(f"No projects yet under {home_dir()}.", file=sys.stderr)
                raise SystemExit(1)
            for entry in entries:
                names = list_project_sessions(Path(entry.cwd))
                label = ", ".join(names) if names else "(no sessions)"
                print(f"{entry.cwd}\t{label}\tupdated {entry.updated_at}")
            raise SystemExit(0)

        if args.command == "clear":
            raise SystemExit(clear_project_session(cwd, session_name))

        if args.command == "history":
            code = show_history(
                cwd,
                config,
                agent_id=getattr(args, "agent_id", None),
                run_id=getattr(args, "run", None),
                session_name=session_name,
                limit=getattr(args, "limit", None),
                json_mode=json_mode,
                local_only=getattr(args, "local", False),
                full_tools=getattr(args, "full", False),
            )
            raise SystemExit(code)

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
                warn_lean_session_resume(
                    cwd,
                    session_name,
                    lean=config.lean,
                    force_new=args.new,
                )
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
                warn_lean_session_resume(
                    cwd,
                    session_name,
                    lean=config.lean,
                    force_new=args.new,
                )
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
                warn_lean_session_resume(
                    cwd,
                    session_name,
                    lean=config.lean,
                    force_new=False,
                )
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

    except (CursorAgentError, SessionCwdMismatchError, ValueError, RuntimeError) as err:
        print(f"error: {format_error(err)}", file=sys.stderr)
        if args.verbose:
            print_error_details(err)
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
