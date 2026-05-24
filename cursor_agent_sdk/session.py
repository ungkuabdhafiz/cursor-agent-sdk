"""Session persistence under ~/.cursor-agent-sdk/ (one store per project path)."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

HOME_DIR_NAME = ".cursor-agent-sdk"
LEGACY_HOME_CONFIG_DIR = Path.home() / ".config" / "cursor-agent-sdk"
PROJECTS_SUBDIR = "projects"
SESSIONS_SUBDIR = "sessions"
SESSION_FILE = "session.json"
META_FILE = "meta.json"
CHAT_LOG_FILE = "chat.jsonl"
HISTORY_FILE = "history"

# Legacy per-repo directories (migrated into the home store on first use).
LEGACY_PROJECT_DIR = ".cursor-agent-sdk"
LEGACY_PROJECT_DIR_OLD = ".cursor-agent"

SESSION_VERSION = 1


@dataclass
class ProjectSession:
    agent_id: str
    cwd: str
    created_at: str
    updated_at: str
    last_mode: str = "agent"
    version: int = SESSION_VERSION
    session_name: str = "default"

    @classmethod
    def create(
        cls,
        *,
        agent_id: str,
        cwd: Path,
        mode: str = "agent",
        session_name: str = "default",
    ) -> ProjectSession:
        now = _now()
        return cls(
            agent_id=agent_id,
            cwd=str(cwd.resolve()),
            created_at=now,
            updated_at=now,
            last_mode=mode,
            version=SESSION_VERSION,
            session_name=session_name,
        )

    def touch(self, *, mode: str | None = None) -> None:
        self.updated_at = _now()
        if mode is not None:
            self.last_mode = mode


@dataclass
class ProjectMeta:
    cwd: str
    project_key: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict) -> ProjectMeta | None:
        cwd = payload.get("cwd")
        project_key = payload.get("project_key")
        if not cwd or not project_key:
            return None
        return cls(
            cwd=str(cwd),
            project_key=str(project_key),
            created_at=str(payload.get("created_at", "")),
            updated_at=str(payload.get("updated_at", "")),
        )


def home_dir() -> Path:
    """Global data directory, e.g. ~/.cursor-agent-sdk/."""
    return Path.home() / HOME_DIR_NAME


def project_key(cwd: Path) -> str:
    """Stable id for a project path (sha256 of resolved cwd)."""
    resolved = os.fsencode(str(cwd.resolve()))
    return hashlib.sha256(resolved).hexdigest()


def project_store_dir(cwd: Path) -> Path:
    """Per-project directory under the home store."""
    _ensure_home_layout()
    _migrate_legacy_config()
    key = project_key(cwd)
    store = home_dir() / PROJECTS_SUBDIR / key
    if not store.exists():
        _migrate_project_local(cwd, store, key)
    else:
        _touch_project_meta(cwd, store, key)
    return store


def project_meta_path(cwd: Path) -> Path:
    return project_store_dir(cwd) / META_FILE


def session_file(cwd: Path, session_name: str = "default") -> Path:
    base = project_store_dir(cwd)
    if session_name == "default":
        return base / SESSION_FILE
    return base / SESSIONS_SUBDIR / f"{session_name}.json"


def chat_history_path(cwd: Path) -> Path:
    return project_store_dir(cwd) / HISTORY_FILE


def chat_log_path(cwd: Path) -> Path:
    return project_store_dir(cwd) / CHAT_LOG_FILE


def list_sessions(cwd: Path) -> list[str]:
    names: list[str] = []
    default_path = session_file(cwd, "default")
    if default_path.is_file():
        names.append("default")
    sessions_path = project_store_dir(cwd) / SESSIONS_SUBDIR
    if sessions_path.is_dir():
        for path in sorted(sessions_path.glob("*.json")):
            names.append(path.stem)
    return names


def list_projects() -> list[ProjectMeta]:
    root = home_dir() / PROJECTS_SUBDIR
    if not root.is_dir():
        return []
    projects: list[ProjectMeta] = []
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        meta = load_project_meta(entry)
        if meta is not None:
            projects.append(meta)
    projects.sort(key=lambda item: item.updated_at, reverse=True)
    return projects


def load_project_meta(store_dir: Path) -> ProjectMeta | None:
    path = store_dir / META_FILE
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return ProjectMeta.from_dict(payload)


def load_session(cwd: Path, session_name: str = "default") -> ProjectSession | None:
    path = session_file(cwd, session_name)
    if not path.is_file():
        return None

    with session_lock(path):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    return _session_from_payload(payload, cwd=cwd, session_name=session_name)


def save_session(cwd: Path, session: ProjectSession) -> None:
    path = session_file(cwd, session.session_name)
    session.version = SESSION_VERSION
    payload = asdict(session)

    with session_lock(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        temp.replace(path)

    _touch_project_meta(cwd, project_store_dir(cwd), project_key(cwd))


def append_chat_log(
    cwd: Path,
    *,
    prompt: str,
    mode: str | None,
    status: str,
    agent_id: str | None = None,
) -> None:
    """Append one interaction line to the project chat log (JSONL)."""
    path = chat_log_path(cwd)
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": _now(),
        "prompt": prompt,
        "mode": mode,
        "status": status,
        "agent_id": agent_id,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def clear_session(cwd: Path, session_name: str = "default") -> bool:
    path = session_file(cwd, session_name)
    if not path.is_file():
        return False
    with session_lock(path):
        path.unlink()
    return True


def validate_session_cwd(session: ProjectSession, cwd: Path) -> None:
    expected = str(cwd.resolve())
    if session.cwd != expected:
        raise SessionCwdMismatchError(
            f"Saved session belongs to {session.cwd!r}, but --cwd is {expected!r}. "
            "Use the correct --cwd, run `cursor-agent-sdk clear`, or pass --new."
        )


class SessionCwdMismatchError(ValueError):
    pass


class SessionNotFoundError(ValueError):
    pass


# Backward-compatible alias used by config and older callers.
def session_dir(cwd: Path) -> Path:
    return project_store_dir(cwd)


@contextlib.contextmanager
def session_lock(path: Path):
    """Exclusive lock for session read/write (best-effort on all platforms)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.touch(exist_ok=True)
    fd = os.open(lock_path, os.O_RDWR)
    try:
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        if sys.platform == "win32":
            import msvcrt

            try:
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _ensure_home_layout() -> None:
    root = home_dir()
    root.mkdir(parents=True, exist_ok=True)
    (root / PROJECTS_SUBDIR).mkdir(parents=True, exist_ok=True)


def _migrate_legacy_config() -> None:
    new_config = home_dir() / "config.toml"
    old_config = LEGACY_HOME_CONFIG_DIR / "config.toml"
    if new_config.is_file() or not old_config.is_file():
        return
    try:
        LEGACY_HOME_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old_config, new_config)
    except OSError:
        pass


def _repo_legacy_dirs(cwd: Path) -> list[Path]:
    """Repo-local legacy folders only (never the global home directory)."""
    root = cwd.resolve()
    home = home_dir().resolve()
    found: list[Path] = []
    for name in (LEGACY_PROJECT_DIR, LEGACY_PROJECT_DIR_OLD):
        local = (root / name).resolve()
        if not local.is_dir():
            continue
        if local == home:
            continue
        try:
            local.relative_to(home)
        except ValueError:
            found.append(local)
        # else: path is inside ~/.cursor-agent-sdk — not a repo-local legacy dir
    return found


def _migrate_project_local(cwd: Path, store: Path, key: str) -> None:
    for local in _repo_legacy_dirs(cwd):
        store.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(local), str(store))
        except OSError:
            shutil.copytree(local, store, dirs_exist_ok=True)
            shutil.rmtree(local, ignore_errors=True)
        _write_project_meta(cwd, store, key)
        return

    store.mkdir(parents=True, exist_ok=True)
    _write_project_meta(cwd, store, key)


def _write_project_meta(cwd: Path, store: Path, key: str) -> None:
    now = _now()
    path = store / META_FILE
    if path.is_file():
        existing = load_project_meta(store)
        created = existing.created_at if existing else now
    else:
        created = now
    meta = ProjectMeta(
        cwd=str(cwd.resolve()),
        project_key=key,
        created_at=created,
        updated_at=now,
    )
    path.write_text(json.dumps(meta.to_dict(), indent=2) + "\n", encoding="utf-8")


def _touch_project_meta(cwd: Path, store: Path, key: str) -> None:
    _write_project_meta(cwd, store, key)


def _session_from_payload(
    payload: dict,
    *,
    cwd: Path,
    session_name: str,
) -> ProjectSession | None:
    agent_id = payload.get("agent_id")
    if not agent_id:
        return None

    version = int(payload.get("version", 0))
    if version > SESSION_VERSION:
        return None

    return ProjectSession(
        agent_id=str(agent_id),
        cwd=payload.get("cwd", str(cwd.resolve())),
        created_at=payload.get("created_at", ""),
        updated_at=payload.get("updated_at", ""),
        last_mode=payload.get("last_mode", "agent"),
        version=version or SESSION_VERSION,
        session_name=payload.get("session_name", session_name),
    )


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
