from __future__ import annotations

from pathlib import Path

from agent_cost_ledger.ledger import CostLedger, load_events_file
from agent_cost_ledger.models import UsageEvent

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_ingest_and_report(tmp_path: Path) -> None:
    book = CostLedger(tmp_path / "ledger-root")
    events = load_events_file(EXAMPLES / "usage_events.jsonl")
    saved = book.append_many(events)
    assert len(saved) == 3

    # e1 has prices on event
    assert saved[0].cost_usd is not None
    assert saved[0].cost_is_partial is False
    # e3 ollama has no price
    assert saved[2].cost_usd is None
    assert saved[2].cost_is_partial is True

    report = book.report(session_id="demo")
    assert report.events == 2
    assert report.input_tokens == 6000
    assert report.cost_usd is not None
    assert report.cost_is_partial is False

    report_all = book.report()
    assert report_all.events == 3
    assert report_all.cost_is_partial is True
    # Must not pretend missing cost is zero total without flag
    assert report_all.cost_usd is not None  # known subset summed
    assert report_all.cost_is_partial is True


def test_price_table_fills_cost(tmp_path: Path) -> None:
    book = CostLedger(tmp_path / "ledger-root")
    book.set_price("ollama", "qwen2.5", input_price_per_1m=0.0, output_price_per_1m=0.0)
    event = UsageEvent(
        provider="ollama",
        model="qwen2.5",
        input_tokens=1000,
        output_tokens=500,
    )
    saved = book.append(event)
    assert saved.cost_usd == 0.0
    assert saved.cost_is_partial is False


def test_unknown_cost_not_zero_without_price(tmp_path: Path) -> None:
    book = CostLedger(tmp_path / "ledger-root")
    event = UsageEvent(
        provider="mystery",
        model="x",
        input_tokens=100,
        output_tokens=50,
    )
    saved = book.append(event)
    assert saved.cost_usd is None
    assert saved.cost_is_partial is True


def test_honor_precomputed_cost(tmp_path: Path) -> None:
    book = CostLedger(tmp_path / "ledger-root")
    event = UsageEvent(
        provider="anthropic",
        model="claude-sonnet",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.42,
    )
    saved = book.append(event)
    assert saved.cost_usd == 0.42
    assert saved.cost_is_partial is False


def test_usage_missing_not_zero_cost(tmp_path: Path) -> None:
    book = CostLedger(tmp_path / "ledger-root")
    book.set_price("openai", "demo", 1.0, 2.0)
    event = UsageEvent(
        provider="openai",
        model="demo",
        input_tokens=0,
        output_tokens=0,
        usage_missing=True,
    )
    saved = book.append(event)
    assert saved.cost_usd is None
    assert saved.cost_is_partial is True


def test_naive_since_does_not_crash(tmp_path: Path) -> None:
    from datetime import datetime

    book = CostLedger(tmp_path / "ledger-root")
    book.append(
        UsageEvent(
            provider="a",
            model="b",
            input_tokens=1,
            output_tokens=1,
            input_price_per_1m=1.0,
            output_price_per_1m=1.0,
        )
    )
    report = book.report(since=datetime(2020, 1, 1))
    assert report.events == 1


def test_load_json_array(tmp_path: Path) -> None:
    path = tmp_path / "arr.json"
    path.write_text(
        """[
          {
            "schema_version": "1",
            "provider": "a",
            "model": "b",
            "input_tokens": 1,
            "output_tokens": 2
          }
        ]""",
        encoding="utf-8",
    )
    events = load_events_file(path)
    assert len(events) == 1
    assert events[0].provider == "a"
