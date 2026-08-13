from __future__ import annotations

from pathlib import Path

from agent_cost_ledger.ingest_cc import load_cc_events, parse_cc_record
from agent_cost_ledger.ledger import CostLedger


def test_parse_and_dedupe(tmp_path: Path) -> None:
    path = tmp_path / "sess.jsonl"
    path.write_text(
        "\n".join(
            [
                '{"type":"user","message":{"role":"user","content":"hi"}}',
                (
                    '{"type":"assistant","timestamp":"2026-07-20T05:15:07.748Z",'
                    '"session_id":"s1","message":{"id":"msg_1","role":"assistant",'
                    '"model":"claude-sonnet","usage":{"input_tokens":10,'
                    '"output_tokens":5,"cache_read_input_tokens":100,'
                    '"cache_creation_input_tokens":20}}}'
                ),
                (
                    '{"type":"assistant","timestamp":"2026-07-20T05:15:07.748Z",'
                    '"session_id":"s1","message":{"id":"msg_1","role":"assistant",'
                    '"model":"claude-sonnet","usage":{"input_tokens":10,'
                    '"output_tokens":5,"cache_read_input_tokens":100,'
                    '"cache_creation_input_tokens":20}}}'
                ),
                '{"type":"assistant","message":{"role":"assistant","content":"x"}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    events = load_cc_events([path], provider="anthropic")
    assert len(events) == 1
    event = events[0]
    assert event.input_tokens == 10
    assert event.output_tokens == 5
    assert event.cache_read_tokens == 100
    assert event.cache_creation_tokens == 20
    assert event.model == "claude-sonnet"
    assert event.session_id == "s1"


def test_ingest_cc_keeps_official_cost(tmp_path: Path) -> None:
    raw = {
        "type": "assistant",
        "message": {
            "id": "msg_cost",
            "role": "assistant",
            "model": "claude-sonnet",
            "usage": {
                "input_tokens": 100,
                "output_tokens": 20,
                "cost_usd": 0.07,
            },
        },
    }
    event = parse_cc_record(raw, provider="anthropic")
    assert event is not None
    saved = CostLedger(tmp_path / "root").append(event)
    assert saved.cost_usd == 0.07
    assert saved.cost_is_partial is False
