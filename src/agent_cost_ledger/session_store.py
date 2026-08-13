from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionStore:
    """Tiny JSON session store for the chat UI (not a full agent memory)."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.sessions_dir = root / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        safe = "".join(c for c in session_id if c.isalnum() or c in "-_")
        if not safe:
            raise ValueError("invalid session id")
        return self.sessions_dir / f"{safe}.json"

    def create(self, title: str = "New chat") -> dict[str, Any]:
        sid = uuid.uuid4().hex[:12]
        data = {
            "id": sid,
            "title": title,
            "created_at": _utcnow(),
            "updated_at": _utcnow(),
            "messages": [],
        }
        self.save(data)
        return data

    def list(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for path in sorted(self.sessions_dir.glob("*.json"), reverse=True):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                items.append(
                    {
                        "id": data.get("id") or path.stem,
                        "title": data.get("title") or "Chat",
                        "updated_at": data.get("updated_at"),
                        "message_count": len(data.get("messages") or []),
                    }
                )
            except Exception:
                continue
        return items

    def get(self, session_id: str) -> dict[str, Any]:
        path = self._path(session_id)
        if not path.exists():
            raise FileNotFoundError(session_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def save(self, data: dict[str, Any]) -> None:
        data["updated_at"] = _utcnow()
        path = self._path(str(data["id"]))
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def delete(self, session_id: str) -> None:
        path = self._path(session_id)
        if path.exists():
            path.unlink()
