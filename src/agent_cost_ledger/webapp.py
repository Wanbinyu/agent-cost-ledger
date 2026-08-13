from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .chat_client import ChatClientError, chat_completion
from .ledger import CostLedger
from .models import UsageEvent
from .session_store import SessionStore
from .settings import ChatSettings, load_settings, save_settings
from .version import __version__

PACKAGE_DIR = Path(__file__).resolve().parent
STATIC_DIR = PACKAGE_DIR / "static"
TEMPLATE_FILE = PACKAGE_DIR / "templates" / "chat.html"


class SettingsUpdate(BaseModel):
    provider: str = "openai"
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "gpt-4o-mini"
    input_price_per_1m: float | None = None
    output_price_per_1m: float | None = None
    # If true and api_key empty, keep existing key
    keep_existing_key: bool = True


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str = Field(..., min_length=1)
    # optional override for one-shot
    model: str | None = None


def create_app(data_dir: Path | None = None) -> FastAPI:
    app = FastAPI(title="agent-cost-ledger chat", version=__version__)
    state: dict[str, Any] = {"data_dir": data_dir}

    def _settings() -> ChatSettings:
        return load_settings(state["data_dir"])

    def _ledger(settings: ChatSettings | None = None) -> CostLedger:
        s = settings or _settings()
        return CostLedger(s.resolved_data_dir())

    def _sessions(settings: ChatSettings | None = None) -> SessionStore:
        s = settings or _settings()
        return SessionStore(s.resolved_data_dir())

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        html = TEMPLATE_FILE.read_text(encoding="utf-8")
        html = html.replace("{{VERSION}}", __version__)
        return HTMLResponse(html)

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        s = _settings()
        return {
            "ok": True,
            "version": __version__,
            "ready": s.is_ready(),
        }

    @app.get("/api/settings")
    async def get_settings() -> dict[str, Any]:
        return _settings().public_dict()

    @app.post("/api/settings")
    async def post_settings(body: SettingsUpdate) -> dict[str, Any]:
        current = _settings()
        api_key = body.api_key.strip()
        if not api_key and body.keep_existing_key:
            api_key = current.api_key
        updated = ChatSettings(
            provider=body.provider.strip() or "openai",
            base_url=(body.base_url or current.base_url).rstrip("/"),
            api_key=api_key,
            model=body.model.strip() or current.model,
            input_price_per_1m=body.input_price_per_1m,
            output_price_per_1m=body.output_price_per_1m,
            data_dir=str(current.resolved_data_dir()),
        )
        save_settings(updated)
        # Persist prices into ledger table when provided
        if (
            updated.input_price_per_1m is not None
            and updated.output_price_per_1m is not None
        ):
            _ledger(updated).set_price(
                updated.provider,
                updated.model,
                updated.input_price_per_1m,
                updated.output_price_per_1m,
                source="ui",
            )
        return updated.public_dict()

    @app.get("/api/sessions")
    async def list_sessions() -> dict[str, Any]:
        return {"sessions": _sessions().list()}

    @app.post("/api/sessions")
    async def new_session() -> dict[str, Any]:
        return _sessions().create()

    @app.get("/api/sessions/{session_id}")
    async def get_session(session_id: str) -> dict[str, Any]:
        try:
            return _sessions().get(session_id)
        except FileNotFoundError as exc:
            raise HTTPException(404, "session not found") from exc

    @app.delete("/api/sessions/{session_id}")
    async def delete_session(session_id: str) -> dict[str, Any]:
        _sessions().delete(session_id)
        return {"ok": True}

    @app.get("/api/usage")
    async def usage(session_id: str | None = None) -> dict[str, Any]:
        report = _ledger().report(session_id=session_id)
        return report.model_dump(mode="json")

    @app.post("/api/chat")
    async def chat(body: ChatRequest) -> dict[str, Any]:
        settings = _settings()
        if body.model:
            settings = settings.model_copy(update={"model": body.model})

        store = _sessions(settings)
        if body.session_id:
            try:
                session = store.get(body.session_id)
            except FileNotFoundError as exc:
                raise HTTPException(404, "session not found") from exc
        else:
            session = store.create(
                title=(body.message[:40] + "…") if len(body.message) > 40 else body.message
            )

        messages = list(session.get("messages") or [])
        messages.append({"role": "user", "content": body.message})

        # Provider only needs role/content
        api_messages = [
            {"role": m["role"], "content": m["content"]}
            for m in messages
            if m.get("role") in {"system", "user", "assistant"}
        ]

        try:
            result = await chat_completion(settings, api_messages)
        except ChatClientError as exc:
            raise HTTPException(
                status_code=exc.status_code or 502,
                detail=str(exc),
            ) from exc

        assistant_msg = {
            "role": "assistant",
            "content": result["content"],
            "input_tokens": result["input_tokens"],
            "output_tokens": result["output_tokens"],
            "model": result["raw_model"],
        }
        messages.append(assistant_msg)
        session["messages"] = messages
        if session.get("title") in {None, "", "New chat"} and body.message:
            session["title"] = body.message[:48]
        store.save(session)

        # Auto-record usage — no manual cost-ledger add
        event = UsageEvent(
            provider=settings.provider,
            model=result["raw_model"] or settings.model,
            input_tokens=result["input_tokens"],
            output_tokens=result["output_tokens"],
            cache_read_tokens=int(result.get("cache_read_tokens") or 0),
            cache_creation_tokens=int(result.get("cache_creation_tokens") or 0),
            session_id=session["id"],
            run_id=session["id"],
            role="chat",
            input_price_per_1m=settings.input_price_per_1m,
            output_price_per_1m=settings.output_price_per_1m,
            usage_missing=bool(result.get("usage_missing")),
            cost_usd=result.get("cost_usd"),
            notes="auto from chat UI",
        )
        saved = _ledger(settings).append(event)
        session_report = _ledger(settings).report(session_id=session["id"])
        total_report = _ledger(settings).report()

        return {
            "session_id": session["id"],
            "message": assistant_msg,
            "usage_event": saved.model_dump(mode="json"),
            "session_usage": session_report.model_dump(mode="json"),
            "total_usage": total_report.model_dump(mode="json"),
            "settings": settings.public_dict(),
        }

    return app
