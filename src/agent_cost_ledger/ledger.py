from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .models import ModelBreakdown, PriceEntry, UsageEvent, UsageReport, as_utc


class CostLedger:
    """Append-only JSONL ledger + optional prices.json."""

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root else Path.cwd() / ".cost-ledger"
        self.ledger_path = self.root / "ledger.jsonl"
        self.prices_path = self.root / "prices.json"

    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        if not self.ledger_path.exists():
            self.ledger_path.write_text("", encoding="utf-8")
        if not self.prices_path.exists():
            self.prices_path.write_text("{}\n", encoding="utf-8")

    # ---- prices ----

    def load_prices(self) -> dict[str, PriceEntry]:
        self.ensure()
        raw = json.loads(self.prices_path.read_text(encoding="utf-8") or "{}")
        return {k: PriceEntry.model_validate(v) for k, v in raw.items()}

    def save_prices(self, prices: dict[str, PriceEntry]) -> None:
        self.ensure()
        payload = {k: v.model_dump() for k, v in sorted(prices.items())}
        self.prices_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def set_price(
        self,
        provider: str,
        model: str,
        input_price_per_1m: float,
        output_price_per_1m: float,
        source: str = "manual",
        cache_read_price_per_1m: float | None = None,
        cache_creation_price_per_1m: float | None = None,
    ) -> str:
        key = f"{provider}/{model}"
        prices = self.load_prices()
        prices[key] = PriceEntry(
            input_price_per_1m=input_price_per_1m,
            output_price_per_1m=output_price_per_1m,
            cache_read_price_per_1m=cache_read_price_per_1m,
            cache_creation_price_per_1m=cache_creation_price_per_1m,
            source=source,
        )
        self.save_prices(prices)
        return key

    # ---- events ----

    def resolve_cost(self, event: UsageEvent) -> UsageEvent:
        """Fill cost_usd from prices or keep a provided total; never invent $0."""
        inp = event.input_price_per_1m
        out = event.output_price_per_1m
        cache_read_p = event.cache_read_price_per_1m
        cache_create_p = event.cache_creation_price_per_1m

        if (
            inp is None
            or out is None
            or (event.cache_read_tokens and cache_read_p is None)
            or (event.cache_creation_tokens and cache_create_p is None)
        ):
            table = self.load_prices()
            entry = table.get(event.model_key())
            if entry:
                if inp is None:
                    inp = entry.input_price_per_1m
                if out is None:
                    out = entry.output_price_per_1m
                if cache_read_p is None:
                    cache_read_p = entry.cache_read_price_per_1m
                if cache_create_p is None:
                    cache_create_p = entry.cache_creation_price_per_1m

        filled = {
            "input_price_per_1m": inp,
            "output_price_per_1m": out,
            "cache_read_price_per_1m": cache_read_p,
            "cache_creation_price_per_1m": cache_create_p,
        }

        if event.usage_missing:
            if event.cost_usd is not None:
                return event.model_copy(
                    update={**filled, "cost_is_partial": False}
                )
            return event.model_copy(
                update={**filled, "cost_usd": None, "cost_is_partial": True}
            )

        can_compute = inp is not None and out is not None
        cache_incomplete = (
            event.cache_read_tokens > 0 and cache_read_p is None
        ) or (event.cache_creation_tokens > 0 and cache_create_p is None)

        if not can_compute:
            if event.cost_usd is not None:
                return event.model_copy(
                    update={**filled, "cost_is_partial": cache_incomplete}
                )
            return event.model_copy(
                update={**filled, "cost_usd": None, "cost_is_partial": True}
            )

        assert inp is not None and out is not None
        cost = (event.input_tokens / 1_000_000.0) * inp + (
            event.output_tokens / 1_000_000.0
        ) * out
        if cache_read_p is not None:
            cost += (event.cache_read_tokens / 1_000_000.0) * cache_read_p
        if cache_create_p is not None:
            cost += (event.cache_creation_tokens / 1_000_000.0) * cache_create_p

        return event.model_copy(
            update={
                **filled,
                "cost_usd": cost,
                "cost_is_partial": cache_incomplete,
            }
        )

    def existing_ids(self) -> set[str]:
        return {event.event_id for event in self.load_events() if event.event_id}

    def append(self, event: UsageEvent) -> UsageEvent:
        self.ensure()
        resolved = self.resolve_cost(event)
        line = resolved.model_dump_json() + "\n"
        with self.ledger_path.open("a", encoding="utf-8") as fh:
            fh.write(line)
        return resolved

    def append_many(
        self,
        events: Iterable[UsageEvent],
        *,
        skip_existing: bool = False,
    ) -> list[UsageEvent]:
        seen = self.existing_ids() if skip_existing else set()
        saved: list[UsageEvent] = []
        for event in events:
            if skip_existing and event.event_id and event.event_id in seen:
                continue
            resolved = self.append(event)
            saved.append(resolved)
            if resolved.event_id:
                seen.add(resolved.event_id)
        return saved

    def load_events(self) -> list[UsageEvent]:
        self.ensure()
        events: list[UsageEvent] = []
        text = self.ledger_path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                events.append(UsageEvent.model_validate_json(line))
            except Exception as exc:  # noqa: BLE001
                raise ValueError(
                    f"invalid ledger line {line_no}: {exc}"
                ) from exc
        return events

    def report(
        self,
        *,
        session_id: str | None = None,
        run_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> UsageReport:
        events = self.load_events()
        since_u = as_utc(since) if since else None
        until_u = as_utc(until) if until else None
        filtered: list[UsageEvent] = []
        for event in events:
            ts = as_utc(event.ts)
            if session_id and event.session_id != session_id:
                continue
            if run_id and event.run_id != run_id:
                continue
            if provider and event.provider != provider:
                continue
            if model and event.model != model:
                continue
            if since_u and ts < since_u:
                continue
            if until_u and ts > until_u:
                continue
            filtered.append(event)

        by_model: dict[str, ModelBreakdown] = {}
        by_session: dict[str, dict] = {}
        total_in = 0
        total_out = 0
        total_cache_read = 0
        total_cache_create = 0
        total_cost = 0.0
        any_cost = False
        partial = False

        for event in filtered:
            total_in += event.input_tokens
            total_out += event.output_tokens
            total_cache_read += event.cache_read_tokens
            total_cache_create += event.cache_creation_tokens
            if event.cost_usd is None or event.cost_is_partial:
                partial = True
            if event.cost_usd is not None and not event.cost_is_partial:
                total_cost += event.cost_usd
                any_cost = True
            elif event.cost_usd is not None and event.cost_is_partial:
                # Count known subset, keep partial flag.
                total_cost += event.cost_usd
                any_cost = True

            key = event.model_key()
            row = by_model.get(key)
            if row is None:
                row = ModelBreakdown(provider=event.provider, model=event.model)
                by_model[key] = row
            row.calls += 1
            row.input_tokens += event.input_tokens
            row.output_tokens += event.output_tokens
            row.cache_read_tokens += event.cache_read_tokens
            row.cache_creation_tokens += event.cache_creation_tokens
            if event.cost_usd is None or event.cost_is_partial:
                row.cost_is_partial = True
            if event.cost_usd is not None:
                row.cost_usd = (row.cost_usd or 0.0) + event.cost_usd

            sid = event.session_id or "(none)"
            s = by_session.setdefault(
                sid,
                {
                    "events": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cache_read_tokens": 0,
                    "cache_creation_tokens": 0,
                    "cost_usd": None,
                    "cost_is_partial": False,
                },
            )
            s["events"] += 1
            s["input_tokens"] += event.input_tokens
            s["output_tokens"] += event.output_tokens
            s["cache_read_tokens"] += event.cache_read_tokens
            s["cache_creation_tokens"] += event.cache_creation_tokens
            if event.cost_usd is None or event.cost_is_partial:
                s["cost_is_partial"] = True
            if event.cost_usd is not None:
                s["cost_usd"] = (s["cost_usd"] or 0.0) + event.cost_usd

        cost_is_partial = False
        if filtered:
            cost_is_partial = partial or not any_cost

        return UsageReport(
            events=len(filtered),
            input_tokens=total_in,
            output_tokens=total_out,
            cache_read_tokens=total_cache_read,
            cache_creation_tokens=total_cache_create,
            cost_usd=total_cost if any_cost else None,
            cost_is_partial=cost_is_partial,
            by_model=sorted(
                by_model.values(),
                key=lambda m: f"{m.provider}/{m.model}",
            ),
            by_session=by_session,
            filters={
                "session_id": session_id,
                "run_id": run_id,
                "since": since_u.isoformat() if since_u else None,
                "until": until_u.isoformat() if until_u else None,
                "provider": provider,
                "model": model,
            },
        )


def load_events_file(path: Path) -> list[UsageEvent]:
    """Load JSONL or a JSON array of events."""
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if text.startswith("["):
        data = json.loads(text)
        return [UsageEvent.model_validate(item) for item in data]
    events: list[UsageEvent] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            events.append(UsageEvent.model_validate_json(line))
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"{path}:{line_no}: {exc}") from exc
    return events
