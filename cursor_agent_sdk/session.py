import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


SESSION_DIR = ".cursor-agent"
SESSION_FILE = "session.json"


@dataclass
class ProjectSession:
    agent_id: str
    cwd: str
    created_at: str
    updated_at: str
    last_mode: str = "agent"

    @classmethod
    def create(cls, *, agent_id: str, cwd: Path, mode: str = "agent") -> "ProjectSession":
        now = _now()
        return cls(
            agent_id=agent_id,
            cwd=str(cwd.resolve()),
            created_at=now,
            updated_at=now,
            last_mode=mode,
        )

    def touch(self, *, mode: str | None = None) -> None:
        self.updated_at = _now()
        if mode is not None:
            self.last_mode = mode


def session_file(cwd: Path) -> Path:
    return cwd.resolve() / SESSION_DIR / SESSION_FILE


def load_session(cwd: Path) -> ProjectSession | None:
    path = session_file(cwd)
    if not path.is_file():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    agent_id = payload.get("agent_id")
    if not agent_id:
        return None

    return ProjectSession(
        agent_id=agent_id,
        cwd=payload.get("cwd", str(cwd.resolve())),
        created_at=payload.get("created_at", ""),
        updated_at=payload.get("updated_at", ""),
        last_mode=payload.get("last_mode", "agent"),
    )


def save_session(cwd: Path, session: ProjectSession) -> None:
    path = session_file(cwd)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(session), indent=2) + "\n", encoding="utf-8")


def clear_session(cwd: Path) -> bool:
    path = session_file(cwd)
    if not path.is_file():
        return False
    path.unlink()
    return True


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
