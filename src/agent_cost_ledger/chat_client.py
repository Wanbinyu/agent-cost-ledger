from __future__ import annotations

from typing import Any

import httpx

from .settings import ChatSettings


class ChatClientError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


async def chat_completion(
    settings: ChatSettings,
    messages: list[dict[str, str]],
    *,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """Call an OpenAI-compatible /chat/completions endpoint.

    Returns normalized dict:
      content, input_tokens, output_tokens, raw_model, finish_reason
    """
    if not settings.is_ready():
        raise ChatClientError(
            "Not configured. Set OPENAI_API_KEY (or COST_LEDGER_API_KEY) "
            "and model, or open the setup panel once."
        )

    url = settings.base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": settings.model,
        "messages": messages,
        "stream": False,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, headers=headers, json=body)
    except httpx.RequestError as exc:
        raise ChatClientError(f"Network error: {exc}") from exc

    if resp.status_code >= 400:
        detail = resp.text[:500]
        raise ChatClientError(
            f"Provider HTTP {resp.status_code}: {detail}",
            status_code=resp.status_code,
        )

    try:
        data = resp.json()
    except Exception as exc:
        raise ChatClientError(f"Invalid JSON from provider: {exc}") from exc

    content = ""
    finish_reason = None
    choices = data.get("choices") or []
    if choices:
        msg = choices[0].get("message") or {}
        content = msg.get("content") or ""
        finish_reason = choices[0].get("finish_reason")

    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}

    def _tok(*keys: str) -> int | None:
        for key in keys:
            if key in usage and usage[key] is not None:
                try:
                    return int(usage[key])
                except (TypeError, ValueError):
                    return None
        return None

    input_tokens = _tok("prompt_tokens", "input_tokens")
    output_tokens = _tok("completion_tokens", "output_tokens")
    cache_read = _tok("cache_read_input_tokens", "cache_read_tokens")
    cache_creation = _tok("cache_creation_input_tokens", "cache_creation_tokens")
    usage_missing = (
        input_tokens is None
        and output_tokens is None
        and cache_read is None
        and cache_creation is None
    )

    return {
        "content": content,
        "input_tokens": input_tokens or 0,
        "output_tokens": output_tokens or 0,
        "cache_read_tokens": cache_read or 0,
        "cache_creation_tokens": cache_creation or 0,
        "raw_model": data.get("model") or settings.model,
        "finish_reason": finish_reason,
        "usage_missing": usage_missing,
        "cost_usd": None,
    }
