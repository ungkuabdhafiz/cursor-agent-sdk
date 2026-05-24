"""Agent lifecycle: create, resume, send, and interactive chat."""

from __future__ import annotations

import signal
import sys
from pathlib import Path
from typing import Literal

from cursor_sdk import Agent, CursorAgentError, CursorClient, SendOptions

from cursor_agent_sdk.chat_input import read_chat_input
from cursor_agent_sdk.config import ToolConfig, build_agent_options, require_api_key
from cursor_agent_sdk.output import print_run_summary, stream_run
from cursor_agent_sdk.session import (
    ProjectSession,
    SessionCwdMismatchError,
    append_chat_log,
    chat_history_path,
    clear_session,
    list_sessions,
    load_session,
    project_store_dir,
    save_session,
    validate_session_cwd,
)

Mode = Literal["agent", "plan"]

_CURRENT_RUN: list = []


class AgentTool:
    def __init__(
        self,
        cwd: Path,
        config: ToolConfig,
        *,
        fast: bool | None = None,
        show_tools: bool | None = None,
        show_meta: bool | None = None,
        json_mode: bool = False,
        session_name: str | None = None,
    ) -> None:
        self.cwd = cwd.resolve()
        self.config = config.merge_cli(
            fast=fast,
            show_tools=show_tools,
            show_meta=show_meta,
            session_name=session_name,
        )
        self.json_mode = json_mode
        self.show_tools = self.config.show_tools
        self.show_meta = self.config.show_meta
        self._agent: Agent | None = None
        self._client: CursorClient | None = None
        self._owns_agent = False
        self._previous_sigint = None

    @property
    def session_name(self) -> str:
        return self.config.session_name

    def close(self) -> None:
        self._restore_sigint()
        self._close_agent()
        if self._client is not None:
            self._client.close()
            self._client = None

    def _close_agent(self) -> None:
        if self._agent is not None and self._owns_agent:
            self._agent.close()
        self._agent = None
        self._owns_agent = False

    def _ensure_client(self) -> CursorClient:
        if self._client is None:
            require_api_key()
            self._client = CursorClient.launch_bridge(workspace=str(self.cwd))
        return self._client

    def __enter__(self) -> AgentTool:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def open_new(self, *, mode: Mode = "agent") -> Agent:
        self._close_agent()
        client = self._ensure_client()
        self._agent = Agent.create(
            build_agent_options(self.cwd, self.config, mode=mode),
            client=client,
        )
        self._owns_agent = True
        session = ProjectSession.create(
            agent_id=self._agent.agent_id,
            cwd=self.cwd,
            mode=mode,
            session_name=self.session_name,
        )
        save_session(self.cwd, session)
        if self.show_meta and not self.json_mode:
            self._print_agent_header(session, mode=mode, resumed=False)
        return self._agent

    def open_existing(self, agent_id: str | None = None) -> Agent:
        session = load_session(self.cwd, self.session_name)
        target_id = agent_id or (session.agent_id if session else None)
        if not target_id:
            raise CursorAgentError(
                "No saved session for this project. Run `cursor-agent-sdk plan` or "
                "`cursor-agent-sdk ask` first, or pass --new to start fresh.",
                code="missing_session",
            )

        if session is not None:
            validate_session_cwd(session, self.cwd)

        self._close_agent()
        client = self._ensure_client()
        options = build_agent_options(self.cwd, self.config)
        self._agent = Agent.resume(target_id, options, client=client)
        self._owns_agent = True

        if session is None or session.agent_id != target_id:
            session = ProjectSession.create(
                agent_id=target_id,
                cwd=self.cwd,
                session_name=self.session_name,
            )
        save_session(self.cwd, session)

        if self.show_meta and not self.json_mode:
            self._print_agent_header(session, mode=session.last_mode, resumed=True)
        return self._agent

    def send(self, prompt: str, *, mode: Mode | None = None) -> int:
        if self._agent is None:
            raise CursorAgentError(
                "Agent is not open. This is an internal error.",
                code="agent_not_open",
            )

        send_mode = mode
        options = SendOptions(mode=send_mode) if send_mode else None
        run = self._agent.send(prompt, options)

        self._install_cancel_handler(run)

        try:
            streamed_text = stream_run(
                run,
                show_tools=self.show_tools,
                show_meta=self.show_meta,
                json_mode=self.json_mode,
                verbose_tools=self.show_meta,
            )
            result = run.wait()
        except KeyboardInterrupt:
            self._cancel_run(run)
            if not self.json_mode:
                print("\nRun cancelled.", file=sys.stderr)
            return 3
        finally:
            self._restore_sigint()

        session = load_session(self.cwd, self.session_name)
        if session is not None:
            session.touch(mode=send_mode or session.last_mode)
            save_session(self.cwd, session)

        print_run_summary(
            result,
            streamed_text=streamed_text,
            json_mode=self.json_mode,
            agent_id=self._agent.agent_id,
            run_id=run.id,
        )

        append_chat_log(
            self.cwd,
            prompt=prompt,
            mode=send_mode,
            status=result.status,
            agent_id=self._agent.agent_id,
        )

        if result.status == "error":
            return 2
        if result.status == "cancelled":
            return 3
        return 0

    def run_once(
        self,
        prompt: str,
        *,
        mode: Mode = "agent",
        new_session: bool = False,
    ) -> int:
        try:
            if new_session:
                self.open_new(mode=mode)
            else:
                session = load_session(self.cwd, self.session_name)
                if session is None:
                    self.open_new(mode=mode)
                else:
                    validate_session_cwd(session, self.cwd)
                    self.open_existing(session.agent_id)
            return self.send(prompt, mode=mode if new_session else None)
        finally:
            self.close()

    def _print_agent_header(
        self,
        session: ProjectSession,
        *,
        mode: str,
        resumed: bool,
    ) -> None:
        from cursor_agent_sdk.model import format_model

        action = "Resumed" if resumed else "Created"
        print(f"{action} agent: {session.agent_id}", file=sys.stderr)
        print(f"Project: {session.cwd}", file=sys.stderr)
        print(f"Session: {session.session_name}", file=sys.stderr)
        print(f"Mode: {mode}", file=sys.stderr)
        if self._agent and self._agent.model:
            print(f"Model: {format_model(self._agent.model)}", file=sys.stderr)
        print(file=sys.stderr)

    def _install_cancel_handler(self, run) -> None:
        global _CURRENT_RUN
        _CURRENT_RUN = [run]

        def handler(signum, frame):
            self._cancel_run(run)
            raise KeyboardInterrupt

        try:
            self._previous_sigint = signal.signal(signal.SIGINT, handler)
        except (ValueError, OSError):
            self._previous_sigint = None

    def _restore_sigint(self) -> None:
        global _CURRENT_RUN
        _CURRENT_RUN = []
        if self._previous_sigint is not None:
            try:
                signal.signal(signal.SIGINT, self._previous_sigint)
            except (ValueError, OSError):
                pass
            self._previous_sigint = None

    def _cancel_run(self, run) -> None:
        try:
            run.cancel()
        except Exception:
            pass


def run_chat(
    cwd: Path,
    config: ToolConfig,
    *,
    fast: bool | None = None,
    show_tools: bool | None = None,
    show_meta: bool | None = None,
    json_mode: bool = False,
    initial_mode: Mode = "plan",
    force_new: bool = False,
    session_name: str | None = None,
) -> int:
    _setup_readline(cwd)

    if not json_mode:
        print(
            "Interactive Cursor SDK session.\n"
            "Commands: /plan, /agent, /new, /session, /clear, /paste, /help, /quit\n"
            "Multiline: paste directly, or type /paste and end with a lone '.'\n",
            file=sys.stderr,
        )

    exit_code = 0
    current_mode: Mode = initial_mode

    with AgentTool(
        cwd,
        config,
        fast=fast,
        show_tools=show_tools,
        show_meta=show_meta,
        json_mode=json_mode,
        session_name=session_name,
    ) as tool:
        if force_new:
            tool.open_new(mode=current_mode)
        else:
            session = load_session(cwd, tool.session_name)
            if session is None:
                tool.open_new(mode=current_mode)
            else:
                try:
                    validate_session_cwd(session, cwd)
                    tool.open_existing(session.agent_id)
                except SessionCwdMismatchError as err:
                    print(f"error: {err}", file=sys.stderr)
                    return 1

        while True:
            try:
                raw = read_chat_input()
            except KeyboardInterrupt:
                if not json_mode:
                    print(file=sys.stderr)
                break

            if raw is None:
                if not json_mode:
                    print(file=sys.stderr)
                break

            prompt = raw.strip()
            if not prompt:
                continue

            lowered = prompt.lower()
            if lowered in {"/quit", "/exit", "/q"}:
                break
            if lowered == "/help":
                _print_help()
                continue
            if lowered == "/session":
                _print_session(cwd, tool.session_name)
                continue
            if lowered in {"/clear", "/reset"}:
                clear_session(cwd, tool.session_name)
                current_mode = "plan"
                tool.open_new(mode=current_mode)
                if not json_mode:
                    print("Cleared session and started fresh.", file=sys.stderr)
                continue
            if lowered == "/new":
                current_mode = "plan"
                tool.open_new(mode=current_mode)
                continue
            if lowered == "/plan":
                current_mode = "plan"
                if not json_mode:
                    print("Next message will use plan mode.", file=sys.stderr)
                continue
            if lowered == "/agent":
                current_mode = "agent"
                if not json_mode:
                    print("Next message will use agent mode.", file=sys.stderr)
                continue

            exit_code = tool.send(prompt, mode=current_mode)
            if exit_code != 0 and not json_mode:
                print(f"Run ended with status code {exit_code}.", file=sys.stderr)

    return exit_code


def read_prompt_arg(prompt: str) -> str:
    if prompt == "-":
        data = sys.stdin.read()
        if not data.strip():
            raise ValueError("stdin prompt is empty")
        return data.rstrip("\n")
    return prompt


def clear_project_session(cwd: Path, session_name: str = "default") -> int:
    if clear_session(cwd, session_name):
        label = "default" if session_name == "default" else session_name
        print(f"Cleared session {label!r}.", file=sys.stderr)
        return 0
    print("No saved session to clear.", file=sys.stderr)
    return 1


def _setup_readline(cwd: Path) -> None:
    try:
        import readline
    except ImportError:
        return

    histfile = chat_history_path(cwd)
    try:
        histfile.parent.mkdir(parents=True, exist_ok=True)
        readline.read_history_file(histfile)
    except (OSError, FileNotFoundError):
        pass

    import atexit

    def save_history() -> None:
        try:
            readline.write_history_file(histfile)
        except OSError:
            pass

    atexit.register(save_history)


def _print_help() -> None:
    print(
        "Usage in chat:\n"
        "  Describe what you want to build or change.\n"
        "  Start with /plan, ask for a proposal, then /agent and ask to implement.\n"
        "\n"
        "Commands:\n"
        "  /plan       Switch to plan mode for the next message\n"
        "  /agent      Switch to agent mode for the next message\n"
        "  /new        Start a fresh SDK session\n"
        "  /clear      Clear saved session and start fresh\n"
        "  /session    Show saved session for this project\n"
        "  /paste      Enter multiline mode (end with a lone '.' on its own line)\n"
        "  /multiline  Alias for /paste\n"
        "  /quit       Exit\n"
        "\n"
        "Multiline paste:\n"
        "  Paste multiple lines directly at the prompt (most terminals), or use /paste.\n",
        file=sys.stderr,
    )


def _print_session(cwd: Path, session_name: str) -> None:
    session = load_session(cwd, session_name)
    if session is None:
        print("No saved session for this project.", file=sys.stderr)
        return

    print(f"Agent ID: {session.agent_id}", file=sys.stderr)
    print(f"Project: {session.cwd}", file=sys.stderr)
    print(f"Store: {project_store_dir(cwd)}", file=sys.stderr)
    print(f"Session: {session.session_name}", file=sys.stderr)
    print(f"Created: {session.created_at}", file=sys.stderr)
    print(f"Updated: {session.updated_at}", file=sys.stderr)
    print(f"Last mode: {session.last_mode}", file=sys.stderr)


def list_project_sessions(cwd: Path) -> list[str]:
    return list_sessions(cwd)
