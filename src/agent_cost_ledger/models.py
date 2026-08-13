from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class PriceEntry(BaseModel):
    input_price_per_1m: float
    output_price_per_1m: float
    cache_read_price_per_1m: float | None = None
    cache_creation_price_per_1m: float | None = None
    currency: str = "USD"
    source: str = "manual"


class UsageEvent(BaseModel):
    schema_version: str = "1"
    event_id: str = Field(default_factory=lambda: uuid4().hex)
    ts: datetime = Field(default_factory=_utcnow)
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    reasoning_tokens: int = 0
    session_id: str | None = None
    run_id: str | None = None
    role: str | None = None
    input_price_per_1m: float | None = None
    output_price_per_1m: float | None = None
    cache_read_price_per_1m: float | None = None
    cache_creation_price_per_1m: float | None = None
    # Populated at ingest time when cost can be computed or was provided.
    cost_usd: float | None = None
    cost_is_partial: bool = False
    usage_missing: bool = False
    notes: str | None = None

    @field_validator("schema_version")
    @classmethod
    def _v1(cls, value: str) -> str:
        if value != "1":
            raise ValueError(f"unsupported schema_version: {value!r}")
        return value

    @field_validator(
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_creation_tokens",
        "reasoning_tokens",
    )
    @classmethod
    def _non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("token counts must be >= 0")
        return value

    @field_validator("ts", mode="before")
    @classmethod
    def _parse_ts(cls, value: Any) -> Any:
        return value

    def model_key(self) -> str:
        return f"{self.provider}/{self.model}"


class ModelBreakdown(BaseModel):
    provider: str
    model: str
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    cost_usd: float | None = None
    cost_is_partial: bool = False


class UsageReport(BaseModel):
    schema_version: str = "1"
    events: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    cost_usd: float | None = None
    cost_is_partial: bool = False
    currency: str = "USD"
    by_model: list[ModelBreakdown] = Field(default_factory=list)
    by_session: dict[str, dict[str, Any]] = Field(default_factory=dict)
    filters: dict[str, Any] = Field(default_factory=dict)
