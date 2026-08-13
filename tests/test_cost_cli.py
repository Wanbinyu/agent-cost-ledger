from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from agent_cost_ledger.cli import app

runner = CliRunner()


def test_demo() -> None:
    result = runner.invoke(app, ["demo"])
    assert result.exit_code == 0
    assert "events" in result.stdout
    assert "ingested" in result.stdout


def test_default_is_report(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "events" in result.stdout
    assert "Usage Chat" not in result.stdout


def test_ingest_cc_cli(tmp_path: Path) -> None:
    src = tmp_path / "proj"
    src.mkdir()
    (src / "a.jsonl").write_text(
        '{"type":"assistant","message":{"id":"m1","role":"assistant",'
        '"model":"claude-sonnet","usage":{"input_tokens":3,"output_tokens":1}}}\n',
        encoding="utf-8",
    )
    ledger = tmp_path / "led"
    result = runner.invoke(
        app,
        ["ingest-cc", str(src), "--ledger", str(ledger)],
    )
    assert result.exit_code == 0
    assert "ingested 1" in result.stdout
    report = runner.invoke(app, ["report", "--ledger", str(ledger), "--json"])
    assert report.exit_code == 0
    assert '"events": 1' in report.stdout
    again = runner.invoke(
        app,
        ["ingest-cc", str(src), "--ledger", str(ledger)],
    )
    assert again.exit_code == 0
    assert "skipped 1" in again.stdout
