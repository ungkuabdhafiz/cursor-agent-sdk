"""Shell completion script generation."""

from __future__ import annotations

SUBCOMMANDS = (
    "plan",
    "ask",
    "send",
    "chat",
    "resume",
    "session",
    "sessions",
    "projects",
    "clear",
    "completion",
)


def completion_script(shell: str) -> str:
    if shell == "bash":
        return _bash_script()
    if shell == "zsh":
        return _zsh_script()
    raise ValueError(f"Unsupported shell: {shell!r}. Use bash or zsh.")


def _bash_script() -> str:
    subs = " ".join(SUBCOMMANDS)
    return f"""# bash completion for cursor-agent-sdk
_cursor_agent_sdk() {{
    local cur prev words cword
    COMPREPLY=()
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    prev="${{COMP_WORDS[COMP_CWORD-1]}}"
    words=("${{COMP_WORDS[@]}}")
    cword=$COMP_CWORD

    local commands="{subs}"
    local global_opts="--cwd --fast --no-tools --verbose --json --lean"
    local global_opts_extra="--model --session --rules --sandbox --codegraph --no-codegraph --help"

    if [[ $cword -eq 1 && "$cur" == -* ]]; then
        COMPREPLY=( $(compgen -W "$global_opts $global_opts_extra" -- "$cur") )
        return 0
    fi

    if [[ $cword -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "$commands $global_opts $global_opts_extra" -- "$cur") )
        return 0
    fi

    case "${{words[1]}}" in
        plan|ask|send|resume|chat|session|sessions|clear|completion)
            if [[ "$cur" == -* ]]; then
                local sub_opts="$global_opts $global_opts_extra --new --mode --start-mode"
                COMPREPLY=( $(compgen -W "$sub_opts" -- "$cur") )
            fi
            ;;
    esac
}}
complete -F _cursor_agent_sdk cursor-agent-sdk
"""


def _zsh_script() -> str:
    subs = " ".join(SUBCOMMANDS)
    return f"""#compdef cursor-agent-sdk

local -a commands global_opts
commands=({subs})
global_opts=(
    '--cwd[Project directory]'
    '--fast[Use Composer fast tier]'
    '--no-tools[Hide tool call lines]'
    '--verbose[Print metadata on stderr]'
    '--json[Machine-readable JSON output]'
    '--lean[Token-efficient defaults]'
    '--codegraph[Enable CodeGraph MCP]'
    '--no-codegraph[Disable CodeGraph MCP]'
    '--model[Model id]'
    '--session[Named session]'
    '--rules[Setting sources: project user team]'
    '--sandbox[Enable sandbox]'
    '--help[Show help]'
)

_arguments -C \\
    '1: :->cmd' \\
    '*:: :->args'

case $state in
    cmd)
        _describe 'command' commands
        _arguments $global_opts
        ;;
    args)
        case $words[1] in
            plan|ask)
                _arguments $global_opts '--new[Force new session]'
                ;;
            send)
                _arguments $global_opts '--mode[plan or agent]:mode:(plan agent)'
                ;;
            chat)
                _arguments $global_opts \\
                    '--start-mode[Initial mode]:mode:(plan agent)' \\
                    '--new[Force new session]'
                ;;
            completion)
                _arguments '1:shell:(bash zsh)'
                ;;
            *)
                _arguments $global_opts
                ;;
        esac
        ;;
esac
"""
