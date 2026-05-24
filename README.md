# cursor-agent-sdk

A CLI for running multi-turn [Cursor SDK](https://cursor.com/docs/sdk/python) agents against any project on your machine. Delegate coding tasks programmatically — plan a feature, review the proposal, then ask the agent to implement it — without using the IDE chat.

Runs bill through the **SDK** (not the IDE agent), so they qualify for SDK Composer pricing and promos.

## Requirements

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) or pip
- A [Cursor API key](https://cursor.com/dashboard/integrations) in `CURSOR_API_KEY`

## Install

```bash
git clone <this-repo>
cd cursor-sdk

python -m venv .venv
uv pip install -e . --python .venv/bin/python
```

Make the command available globally (pick one):

```bash
# Option A: activate the venv in each shell
source .venv/bin/activate

# Option B: symlink into ~/.local/bin (recommended)
ln -sf "$(pwd)/.venv/bin/cursor-agent-sdk" ~/.local/bin/cursor-agent-sdk
```

Verify:

```bash
cursor-agent-sdk --help
```

## Quick start

From any project directory:

```bash
export CURSOR_API_KEY="cursor_..."

# 1. Ask for a plan (explore, propose — no edits by default in plan mode)
cursor-agent-sdk plan "I want to implement OAuth login"

# 2. Follow up to implement
cursor-agent-sdk send --mode agent "Implement the plan you proposed"

# 3. Keep iterating on the same session
cursor-agent-sdk send "Add tests for the auth middleware"
```

Or use interactive chat:

```bash
cursor-agent-sdk chat
```

```
cursor-agent-sdk> /plan
cursor-agent-sdk> I want to implement feature A
cursor-agent-sdk> /agent
cursor-agent-sdk> Go ahead and implement it
cursor-agent-sdk> /quit
```

## Commands

| Command | Description |
|---------|-------------|
| `plan PROMPT` | Start or continue a session in **plan** mode |
| `ask PROMPT` | Start or continue a session in **agent** mode (makes edits) |
| `send PROMPT` | Send a follow-up in the saved session |
| `chat` | Interactive multi-turn REPL |
| `session` | Show the saved agent ID for this project |
| `resume AGENT_ID [PROMPT]` | Resume a specific agent |
| `clear` | Delete the saved session file |

### Flags

| Flag | Description |
|------|-------------|
| `--cwd PATH` | Target project directory (default: current directory) |
| `--fast` | Use Composer fast tier (default: standard via `fast=false`) |
| `--no-tools` | Hide `[tool]` lines in output |
| `--verbose` | Print agent/run metadata on stderr |
| `--new` | Force a fresh SDK session (`plan` / `ask` only) |
| `--mode plan\|agent` | Override mode for a `send` follow-up |

## Multi-turn sessions

Each project gets a session file at `.cursor-agent/session.json` containing the agent ID. Follow-up commands resume that agent so the SDK keeps full conversation context across runs.

```bash
cursor-agent-sdk --cwd ~/projects/my-app plan "Add rate limiting"
cursor-agent-sdk --cwd ~/projects/my-app send --mode agent "Implement it"
```

This is different from the Cursor IDE agent: these runs go through the SDK runtime and are tagged as SDK usage in your [dashboard](https://cursor.com/dashboard/usage).

## Model tier

By default the tool requests **Composer 2.5 standard** tier:

```python
ModelSelection(id="composer-2.5", params=[{"id": "fast", "value": "false"}])
```

Use `--fast` or set `COMPOSER_FAST=true` for the fast tier.

## Environment variables

| Variable | Description |
|----------|-------------|
| `CURSOR_API_KEY` | Required. Your Cursor API key. |
| `COMPOSER_FAST` | Set to `true` to default to fast tier. |

## Project layout

```
cursor-sdk/
├── cursor_agent_sdk/   # Python package
│   ├── cli.py          # Argument parsing
│   ├── tool.py         # Agent create / resume / send
│   ├── session.py      # Per-project session persistence
│   ├── output.py       # Streaming output
│   └── model.py        # Composer model selection
├── pyproject.toml
└── main.py             # Thin entry point
```

## Chat commands

Inside `cursor-agent-sdk chat`:

| Command | Action |
|---------|--------|
| `/plan` | Switch next message to plan mode |
| `/agent` | Switch next message to agent mode |
| `/new` | Start a fresh SDK session |
| `/session` | Show saved session info |
| `/help` | Show help |
| `/quit` | Exit |

## License

MIT (or your chosen license — update as needed)
