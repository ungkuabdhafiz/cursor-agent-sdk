import sys
from pathlib import Path
from typing import Literal

from cursor_sdk import Agent, AgentOptions, CursorAgentError, LocalAgentOptions, SendOptions

from cursor_agent_sdk.model import build_model, format_model
from cursor_agent_sdk.output import print_run_summary, stream_run
from cursor_agent_sdk.session import ProjectSession, clear_session, load_session, save_session

Mode = Literal["agent", "plan"]


class AgentTool:
    def __init__(
        self,
        cwd: Path,
        *,
        fast: bool | None = None,
        show_tools: bool = True,
        show_meta: bool = False,
    ) -> None:
        self.cwd = cwd.resolve()
        self.fast = fast
        self.show_tools = show_tools
        self.show_meta = show_meta
        self._agent: Agent | None = None
        self._owns_agent = False

    def close(self) -> None:
        if self._agent is not None and self._owns_agent:
            self._agent.close()
        self._agent = None
        self._owns_agent = False

    def __enter__(self) -> "AgentTool":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def open_new(self, *, mode: Mode = "agent") -> Agent:
        self.close()
        self._agent = Agent.create(
            AgentOptions(
                model=build_model(fast=self.fast),
                local=LocalAgentOptions(cwd=str(self.cwd)),
                mode=mode,
            )
        )
        self._owns_agent = True
        session = ProjectSession.create(
            agent_id=self._agent.agent_id,
            cwd=self.cwd,
            mode=mode,
        )
        save_session(self.cwd, session)
        if self.show_meta:
            self._print_agent_header(session, mode=mode, resumed=False)
        return self._agent

    def open_existing(self, agent_id: str | None = None) -> Agent:
        session = load_session(self.cwd)
        target_id = agent_id or (session.agent_id if session else None)
        if not target_id:
            raise CursorAgentError(
                "No saved session for this project. Run `cursor-agent-sdk plan` or "
                "`cursor-agent-sdk ask` first, or pass --new to start fresh.",
                code="missing_session",
            )

        self.close()
        self._agent = Agent.resume(
            target_id,
            AgentOptions(
                model=build_model(fast=self.fast),
                local=LocalAgentOptions(cwd=str(self.cwd)),
            ),
        )
        self._owns_agent = True

        if session is None or session.agent_id != target_id:
            session = ProjectSession.create(agent_id=target_id, cwd=self.cwd)
        save_session(self.cwd, session)

        if self.show_meta:
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

        streamed_text = stream_run(
            run,
            show_tools=self.show_tools,
            show_meta=self.show_meta,
        )
        result = run.wait()

        session = load_session(self.cwd)
        if session is not None:
            session.touch(mode=send_mode or session.last_mode)
            save_session(self.cwd, session)

        print_run_summary(result, streamed_text=streamed_text)

        if result.status == "error":
            return 2
        if result.status == "cancelled":
            return 3
        return 0

    def run_once(self, prompt: str, *, mode: Mode = "agent", new_session: bool = False) -> int:
        try:
            if new_session:
                self.open_new(mode=mode)
            else:
                session = load_session(self.cwd)
                if session is None:
                    self.open_new(mode=mode)
                else:
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
        action = "Resumed" if resumed else "Created"
        print(f"{action} agent: {session.agent_id}", file=sys.stderr)
        print(f"Project: {session.cwd}", file=sys.stderr)
        print(f"Mode: {mode}", file=sys.stderr)
        if self._agent and self._agent.model:
            print(f"Model: {format_model(self._agent.model)}", file=sys.stderr)
        print(file=sys.stderr)


def run_chat(
    cwd: Path,
    *,
    fast: bool | None = None,
    show_tools: bool = True,
    show_meta: bool = False,
    initial_mode: Mode = "plan",
) -> int:
    print(
        "Interactive Cursor SDK session.\n"
        "Commands: /plan, /agent, /new, /session, /help, /quit\n",
        file=sys.stderr,
    )

    exit_code = 0
    current_mode: Mode = initial_mode

    with AgentTool(cwd, fast=fast, show_tools=show_tools, show_meta=show_meta) as tool:
        tool.open_new(mode=current_mode)

        while True:
            try:
                prompt = input("cursor-agent-sdk> ").strip()
            except (EOFError, KeyboardInterrupt):
                print(file=sys.stderr)
                break

            if not prompt:
                continue

            lowered = prompt.lower()
            if lowered in {"/quit", "/exit", "/q"}:
                break
            if lowered == "/help":
                _print_help()
                continue
            if lowered == "/session":
                _print_session(cwd)
                continue
            if lowered == "/new":
                current_mode = "plan"
                tool.open_new(mode=current_mode)
                continue
            if lowered == "/plan":
                current_mode = "plan"
                print("Next message will use plan mode.", file=sys.stderr)
                continue
            if lowered == "/agent":
                current_mode = "agent"
                print("Next message will use agent mode.", file=sys.stderr)
                continue

            exit_code = tool.send(prompt, mode=current_mode)
            if exit_code != 0:
                print(f"Run ended with status code {exit_code}.", file=sys.stderr)

    return exit_code


def _print_help() -> None:
    print(
        "Usage in chat:\n"
        "  Describe what you want to build or change.\n"
        "  Start with /plan, ask for a proposal, then /agent and ask to implement.\n"
        "\n"
        "Commands:\n"
        "  /plan     Switch to plan mode for the next message\n"
        "  /agent    Switch to agent mode for the next message\n"
        "  /new      Start a fresh SDK session\n"
        "  /session  Show saved session for this project\n"
        "  /quit     Exit\n",
        file=sys.stderr,
    )


def _print_session(cwd: Path) -> None:
    session = load_session(cwd)
    if session is None:
        print("No saved session for this project.", file=sys.stderr)
        return

    print(f"Agent ID: {session.agent_id}", file=sys.stderr)
    print(f"Project: {session.cwd}", file=sys.stderr)
    print(f"Created: {session.created_at}", file=sys.stderr)
    print(f"Updated: {session.updated_at}", file=sys.stderr)
    print(f"Last mode: {session.last_mode}", file=sys.stderr)


def clear_project_session(cwd: Path) -> int:
    if clear_session(cwd):
        print("Cleared saved session.", file=sys.stderr)
        return 0
    print("No saved session to clear.", file=sys.stderr)
    return 1
