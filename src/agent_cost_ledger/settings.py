from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


def default_data_dir() -> Path:
    return Path.cwd() / ".cost-ledger"


class ChatSettings(BaseModel):
    """Runtime settings for the zero-friction chat UI."""

    provider: str = "openai"
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "gpt-4o-mini"
    input_price_per_1m: float | None = None
    output_price_per_1m: float | None = None
    data_dir: str = ""

    def resolved_data_dir(self) -> Path:
        if self.data_dir:
            return Path(self.data_dir)
        return default_data_dir()

    def is_ready(self) -> bool:
        return bool(self.api_key.strip() and self.model.strip() and self.base_url.strip())

    def public_dict(self) -> dict[str, Any]:
        """Safe for UI — never include full API key."""
        key = self.api_key.strip()
        masked = ""
        if key:
            if len(key) <= 8:
                masked = "*" * len(key)
            else:
                masked = key[:3] + "…" + key[-4:]
        return {
            "provider": self.provider,
            "base_url": self.base_url,
            "model": self.model,
            "has_api_key": bool(key),
            "api_key_masked": masked,
            "input_price_per_1m": self.input_price_per_1m,
            "output_price_per_1m": self.output_price_per_1m,
            "ready": self.is_ready(),
            "data_dir": str(self.resolved_data_dir()),
        }


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def load_settings(data_dir: Path | None = None) -> ChatSettings:
    """Load settings without prompting.

    Priority: process env > data_dir/settings.json > cwd .env (via dotenv if present).
    """
    try:
        from dotenv import load_dotenv

        load_dotenv(Path.cwd() / ".env", override=False)
    except Exception:
        pass

    root = data_dir or default_data_dir()
    file_cfg: dict[str, Any] = {}
    cfg_path = root / "settings.json"
    if cfg_path.exists():
        try:
            file_cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            file_cfg = {}

    api_key = (
        _env("COST_LEDGER_API_KEY")
        or _env("OPENAI_API_KEY")
        or _env("API_KEY")
        or str(file_cfg.get("api_key") or "")
    )
    base_url = (
        _env("COST_LEDGER_BASE_URL")
        or _env("OPENAI_BASE_URL")
        or str(file_cfg.get("base_url") or "https://api.openai.com/v1")
    )
    model = (
        _env("COST_LEDGER_MODEL")
        or _env("OPENAI_MODEL")
        or str(file_cfg.get("model") or "gpt-4o-mini")
    )
    provider = (
        _env("COST_LEDGER_PROVIDER")
        or str(file_cfg.get("provider") or "openai")
    )

    def _price(env_name: str, key: str) -> float | None:
        raw = _env(env_name)
        if raw:
            try:
                return float(raw)
            except ValueError:
                return None
        val = file_cfg.get(key)
        if val is None or val == "":
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    return ChatSettings(
        provider=provider,
        base_url=base_url.rstrip("/"),
        api_key=api_key,
        model=model,
        input_price_per_1m=_price("COST_LEDGER_INPUT_PRICE", "input_price_per_1m"),
        output_price_per_1m=_price("COST_LEDGER_OUTPUT_PRICE", "output_price_per_1m"),
        data_dir=str(root),
    )


def save_settings(settings: ChatSettings) -> Path:
    root = settings.resolved_data_dir()
    root.mkdir(parents=True, exist_ok=True)
    path = root / "settings.json"
    payload = {
        "provider": settings.provider,
        "base_url": settings.base_url,
        "api_key": settings.api_key,
        "model": settings.model,
        "input_price_per_1m": settings.input_price_per_1m,
        "output_price_per_1m": settings.output_price_per_1m,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # Also write a local .env snippet for non-UI CLI users (gitignored via data dir only)
    return path
