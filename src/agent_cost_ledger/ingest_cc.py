"""Ingest Claude Code project transcripts into UsageEvent rows."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .models import UsageEvent, as_utc


def claude_project_slug(cwd: Path | None = None) -> str:
    root = (cwd or Path.cwd()).resolve()
    return str(root).replace(":", "-").replace("\\", "-").replace("/", "-")


def default_claude_project_dir(cwd: Path | None = None) -> Path:
    return Path.home() / ".claude" / "projects" / claude_project_slug(cwd)


def _token(usage: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        if key in usage and usage[key] is not None:
            try:
                return int(usage[key])
            except (TypeError, ValueError):
                return None
    return None


def _parse_ts(raw: Any) -> datetime | None:
    if not raw:
        return None
    text = str(raw).replace("Z", "+00:00")
    try:
        return as_utc(datetime.fromisoformat(text))
    except ValueError:
        return None


def parse_cc_record(
    raw: dict[str, Any],
    *,
    provider: str,
    default_session: str | None = None,
) -> UsageEvent | None:
    kind = str(raw.get("type") or "")
    message = raw.get("message")
    if kind not in {"assistant", "completion"} and not (
        isinstance(message, dict) and message.get("role") == "assistant"
    ):
        return None
    if not isinstance(message, dict):
        return None
    usage = message.get("usage")
    if not isinstance(usage, dict) or not usage:
        top = raw.get("usage")
        usage = top if isinstance(top, dict) else {}
    if not usage:
        return None

    input_tokens = _token(usage, "input_tokens", "prompt_tokens")
    output_tokens = _token(usage, "output_tokens", "completion_tokens")
    cache_read = _token(usage, "cache_read_input_tokens", "cache_read_tokens")
    cache_creation = _token(
        usage, "cache_creation_input_tokens", "cache_creation_tokens"
    )
    reasoning = _token(usage, "reasoning_tokens")
    if (
        input_tokens is None
        and output_tokens is None
        and cache_read is None
        and cache_creation is None
    ):
        return None

    cost = usage.get("cost_usd")
    if cost is None:
        cost = raw.get("cost_usd") or raw.get("total_cost_usd")
    try:
        cost_usd = float(cost) if cost is not None else None
    except (TypeError, ValueError):
        cost_usd = None

    ts = _parse_ts(raw.get("timestamp") or raw.get("ts"))
    session = (
        raw.get("session_id")
        or raw.get("sessionId")
        or default_session
    )
    model = str(message.get("model") or raw.get("model") or "unknown")
    msg_id = str(message.get("id") or raw.get("uuid") or "")

    payload: dict[str, Any] = {
        "provider": provider,
        "model": model,
        "input_tokens": input_tokens or 0,
        "output_tokens": output_tokens or 0,
        "cache_read_tokens": cache_read or 0,
        "cache_creation_tokens": cache_creation or 0,
        "reasoning_tokens": reasoning or 0,
        "session_id": str(session) if session else None,
        "run_id": msg_id or None,
        "role": "assistant",
        "cost_usd": cost_usd,
        "notes": "ingest-cc",
    }
    if ts is not None:
        payload["ts"] = ts
    if msg_id:
        payload["event_id"] = msg_id
    return UsageEvent.model_validate(payload)


def list_claude_projects() -> list[Path]:
    root = Path.home() / ".claude" / "projects"
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if p.is_dir())


def iter_cc_paths(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        files = sorted(path.glob("*.jsonl"))
        if not files:
            files = sorted(
                p for p in path.rglob("*.jsonl") if p.is_file()
            )
        return files
    projects = list_claude_projects()
    hint = ""
    if projects:
        shown = ", ".join(p.name for p in projects[:8])
        hint = f" Nearby projects: {shown}."
    raise FileNotFoundError(
        f"no Claude Code transcripts at {path}.{hint} "
        "Pass a session JSONL or ~/.claude/projects/<slug>."
    )


def load_cc_events(
    paths: Iterable[Path],
    *,
    provider: str = "anthropic",
) -> list[UsageEvent]:
    events: list[UsageEvent] = []
    seen: set[str] = set()
    for path in paths:
        session_hint = path.stem
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(raw, dict):
                continue
            event = parse_cc_record(
                raw, provider=provider, default_session=session_hint
            )
            if event is None:
                continue
            key = event.event_id or f"{path}:{line_no}"
            if key in seen:
                continue
            seen.add(key)
            events.append(event)
    return events
