# cursor-agent-sdk

A CLI and Python library for running multi-turn [Cursor SDK](https://cursor.com/docs/sdk/python) agents against any project on your machine. Delegate coding tasks programmatically — plan a feature, review the proposal, then ask the agent to implement it — without using the IDE chat.

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
uv pip install -e ".[dev]" --python .venv/bin/python
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

From PyPI (when published):

```bash
pip install cursor-agent-sdk
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

# Read prompt from stdin
echo "Refactor the auth module" | cursor-agent-sdk ask -
```

Or use interactive chat (resumes an existing session when present):

```bash
cursor-agent-sdk chat
```

```
cursor-agent-sdk> /plan
cursor-agent-sdk> I want to implement feature A
cursor-agent-sdk> /agent
cursor-agent-sdk> Go ahead and implement it
cursor-agent-sdk> /clear
cursor-agent-sdk> /quit
```

## Commands

| Command | Description |
|---------|-------------|
| `plan PROMPT` | Start or continue a session in **plan** mode (`-` = stdin) |
| `ask PROMPT` | Start or continue a session in **agent** mode (makes edits) |
| `send PROMPT` | Send a follow-up in the saved session |
| `chat` | Interactive multi-turn REPL (resumes saved session) |
| `session` | Show the saved agent ID for this project |
| `sessions` | List named sessions |
| `resume AGENT_ID [PROMPT]` | Resume a specific agent |
| `clear` | Delete the saved session file |
| `completion SHELL` | Print shell completion (`bash` or `zsh`) |

### Flags

| Flag | Description |
|------|-------------|
| `--cwd PATH` | Target project directory (default: current directory) |
| `--session NAME` | Named session (`.cursor-agent-sdk/sessions/NAME.json`) |
| `--model ID` | Model id (default: `composer-2.5`) |
| `--fast` / `--no-fast` | Composer fast vs standard tier |
| `--rules SOURCE ...` | Setting sources: `project`, `user`, `team`, etc. |
| `--sandbox` / `--no-sandbox` | Enable or disable sandbox |
| `--json` | NDJSON stream + final JSON result (for scripts/CI) |
| `--no-tools` | Hide `[tool]` lines in output |
| `--verbose` | Metadata on stderr; verbose tool args/results |
| `--new` | Force a fresh SDK session (`plan` / `ask` / `chat`) |
| `--mode plan\|agent` | Override mode for a `send` follow-up |

## Multi-turn sessions

Each project stores session state under `.cursor-agent-sdk/`:

- Default session: `.cursor-agent-sdk/session.json`
- Named sessions: `.cursor-agent-sdk/sessions/NAME.json`

Existing `.cursor-agent/` directories are renamed automatically on first use.

Sessions include a schema `version`, file locking on read/write, and cwd validation on resume.

```bash
cursor-agent-sdk --cwd ~/projects/my-app --session auth plan "Add login"
cursor-agent-sdk --cwd ~/projects/my-app --session auth send --mode agent "Implement it"
```

## Configuration

Config is merged from (later overrides earlier):

1. `~/.config/cursor-agent-sdk/config.toml` (user defaults)
2. `.cursor-agent-sdk/config.toml` in the project (per-repo overrides)

See [examples/config.toml.example](examples/config.toml.example).

| Variable | Description |
|----------|-------------|
| `CURSOR_API_KEY` | Required. Your Cursor API key. |
| `CURSOR_AGENT_MODEL` | Default model id |
| `COMPOSER_FAST` | Set to `true` to default to fast tier |

## JSON output

For CI and scripting:

```bash
cursor-agent-sdk ask --json "fix lint errors" | tee run.ndjson
```

Streams NDJSON events (`assistant`, `tool_call`, …) and ends with a `{"type":"result",...}` line.

## Shell completion

```bash
# bash
eval "$(cursor-agent-sdk completion bash)"

# zsh
eval "$(cursor-agent-sdk completion zsh)"
```

## Python API

```python
from pathlib import Path
from cursor_agent_sdk import AgentTool, ToolConfig, load_config

config = load_config(Path("/path/to/project"))
with AgentTool(Path("/path/to/project"), config) as tool:
    tool.open_new(mode="plan")
    tool.send("Design a caching layer")
```

## Examples

- [examples/Makefile](examples/Makefile) — plan → implement workflow
- [examples/github-action.yml](examples/github-action.yml) — CI with `--json`
- [examples/config.toml.example](examples/config.toml.example) — config template

## Development

```bash
pip install -e ".[dev]"
ruff check cursor_agent_sdk tests
pytest
```

## Project layout

```
cursor-agent-sdk/
├── cursor_agent_sdk/
│   ├── cli.py          # Argument parsing
│   ├── tool.py         # Agent create / resume / send / chat
│   ├── session.py      # Persistence, locking, named sessions
│   ├── config.py       # TOML + env configuration
│   ├── output.py       # Streaming and JSON output
│   ├── errors.py       # Actionable error hints
│   ├── completion.py   # Shell completion scripts
│   └── model.py        # Model selection
├── tests/
├── examples/
└── pyproject.toml
```

## License

MIT — see [LICENSE](LICENSE).
