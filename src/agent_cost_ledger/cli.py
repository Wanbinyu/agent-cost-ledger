from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from .ingest_cc import default_claude_project_dir, iter_cc_paths, load_cc_events
from .ledger import CostLedger, load_events_file
from .models import UsageEvent, UsageReport, as_utc
from .version import __version__

app = typer.Typer(
    name="cost-ledger",
    help=(
        "Token/cost ledger. Default command is report.\n"
        "Chat UI is optional: pip install 'agent-cost-ledger[web]' && cost-ledger ui"
    ),
    add_completion=False,
    no_args_is_help=False,
    invoke_without_command=True,
)
prices_app = typer.Typer(help="Manage per-model unit prices.")
app.add_typer(prices_app, name="prices")

console = Console()
err_console = Console(stderr=True)


def _ledger_opt() -> Path:
    return Path.cwd() / ".cost-ledger"


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False, "--version", help="Show version and exit.", is_eager=True
    ),
) -> None:
    if version:
        typer.echo(f"agent-cost-ledger {__version__}")
        raise typer.Exit(0)
    if ctx.invoked_subcommand is None:
        _print_report(CostLedger(_ledger_opt()).report())


def ui_entry() -> None:
    """Console script `usage-chat` — optional debug UI."""
    _launch_ui(host="127.0.0.1", port=8765, open_browser=True, ledger_dir=None)


def _launch_ui(
    *,
    host: str,
    port: int,
    open_browser: bool,
    ledger_dir: Path | None,
) -> None:
    try:
        from .serve import serve
    except ImportError as exc:
        err_console.print(
            "[red]error:[/red] chat UI extras not installed. "
            "Run: pip install 'agent-cost-ledger[web]'"
        )
        raise typer.Exit(1) from exc

    if host not in {"127.0.0.1", "localhost", "::1"}:
        err_console.print(
            f"[yellow]warning:[/yellow] binding {host} exposes the local API key. "
            "Prefer 127.0.0.1."
        )

    root = ledger_dir or _ledger_opt()
    console.print(
        f"[bold]Usage Chat[/bold]  http://{host}:{port}/\n"
        f"[dim]debug only — does not see Claude Code traffic · data: {root}[/dim]"
    )
    serve(host=host, port=port, open_browser=open_browser, data_dir=root)


@app.command("ui")
def ui_cmd(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port"),
    no_open: bool = typer.Option(False, "--no-open", help="Do not open browser"),
    ledger_dir: Path = typer.Option(None, "--ledger", help="Data directory"),
) -> None:
    """Optional debug chat UI (requires agent-cost-ledger[web])."""
    _launch_ui(
        host=host,
        port=port,
        open_browser=not no_open,
        ledger_dir=ledger_dir,
    )


@app.command("add")
def add_event(
    provider: str = typer.Option(..., "--provider", "-p"),
    model: str = typer.Option(..., "--model", "-m"),
    input_tokens: int = typer.Option(0, "--input-tokens", "-i"),
    output_tokens: int = typer.Option(0, "--output-tokens", "-o"),
    cache_read: int = typer.Option(0, "--cache-read-tokens"),
    cache_creation: int = typer.Option(0, "--cache-creation-tokens"),
    session: Optional[str] = typer.Option(None, "--session", "-s"),
    run_id: Optional[str] = typer.Option(None, "--run-id"),
    role: Optional[str] = typer.Option(None, "--role"),
    input_price: Optional[float] = typer.Option(
        None, "--input-price-per-1m", help="USD per 1M input tokens"
    ),
    output_price: Optional[float] = typer.Option(
        None, "--output-price-per-1m", help="USD per 1M output tokens"
    ),
    cost: Optional[float] = typer.Option(
        None, "--cost-usd", help="Precomputed total (kept when prices are missing)"
    ),
    ledger_dir: Path = typer.Option(
        None, "--ledger", help="Ledger directory (default: ./.cost-ledger)"
    ),
) -> None:
    """Append one usage event."""
    root = ledger_dir or _ledger_opt()
    book = CostLedger(root)
    event = UsageEvent(
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read,
        cache_creation_tokens=cache_creation,
        session_id=session,
        run_id=run_id,
        role=role,
        input_price_per_1m=input_price,
        output_price_per_1m=output_price,
        cost_usd=cost,
    )
    saved = book.append(event)
    typer.echo(saved.model_dump_json(indent=2))


@app.command("ingest")
def ingest(
    path: Path = typer.Argument(..., exists=True, readable=True),
    ledger_dir: Path = typer.Option(None, "--ledger"),
) -> None:
    """Ingest JSONL or JSON array of usage events (ledger schema)."""
    root = ledger_dir or _ledger_opt()
    book = CostLedger(root)
    try:
        events = load_events_file(path)
        saved = book.append_many(events)
    except Exception as exc:  # noqa: BLE001
        err_console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(1) from exc
    typer.echo(f"ingested {len(saved)} event(s) into {book.ledger_path}")


@app.command("ingest-cc")
def ingest_cc(
    path: Optional[Path] = typer.Argument(
        None,
        help="Claude Code transcript JSONL or a projects/<slug> directory",
    ),
    provider: str = typer.Option("anthropic", "--provider", "-p"),
    ledger_dir: Path = typer.Option(None, "--ledger"),
) -> None:
    """Ingest Claude Code project transcripts (message.usage)."""
    root = ledger_dir or _ledger_opt()
    source = path or default_claude_project_dir()
    try:
        files = iter_cc_paths(source)
        events = load_cc_events(files, provider=provider)
        saved = CostLedger(root).append_many(events)
    except Exception as exc:  # noqa: BLE001
        err_console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(1) from exc
    typer.echo(
        f"ingested {len(saved)} Claude Code event(s) from {source} "
        f"into {(ledger_dir or _ledger_opt()) / 'ledger.jsonl'}"
    )


@app.command("report")
def report(
    session: Optional[str] = typer.Option(None, "--session", "-s"),
    run_id: Optional[str] = typer.Option(None, "--run-id"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p"),
    model: Optional[str] = typer.Option(None, "--model", "-m"),
    since: Optional[str] = typer.Option(None, "--since", help="ISO date/datetime"),
    until: Optional[str] = typer.Option(None, "--until", help="ISO date/datetime"),
    as_json: bool = typer.Option(False, "--json"),
    ledger_dir: Path = typer.Option(None, "--ledger"),
) -> None:
    """Aggregate usage and cost (also the default when no subcommand)."""
    root = ledger_dir or _ledger_opt()
    book = CostLedger(root)
    try:
        since_dt = _parse_dt(since) if since else None
        until_dt = _parse_dt(until) if until else None
        usage = book.report(
            session_id=session,
            run_id=run_id,
            since=since_dt,
            until=until_dt,
            provider=provider,
            model=model,
        )
    except Exception as exc:  # noqa: BLE001
        err_console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(1) from exc

    if as_json:
        typer.echo(usage.model_dump_json(indent=2))
        return
    _print_report(usage)


def _print_report(usage: UsageReport) -> None:
    cost_s = (
        f"${usage.cost_usd:.6f}"
        if usage.cost_usd is not None
        else "unknown"
    )
    if usage.cost_is_partial:
        cost_s += " (partial — some events lack prices or usage)"
    console.print(f"[bold]events[/bold]: {usage.events}")
    console.print(f"[bold]input_tokens[/bold]: {usage.input_tokens}")
    console.print(f"[bold]output_tokens[/bold]: {usage.output_tokens}")
    if usage.cache_read_tokens or usage.cache_creation_tokens:
        console.print(f"[bold]cache_read[/bold]: {usage.cache_read_tokens}")
        console.print(f"[bold]cache_creation[/bold]: {usage.cache_creation_tokens}")
    console.print(f"[bold]cost_usd[/bold]: {cost_s}")

    if usage.by_model:
        table = Table(title="by model")
        table.add_column("provider/model")
        table.add_column("calls", justify="right")
        table.add_column("in", justify="right")
        table.add_column("out", justify="right")
        table.add_column("cost", justify="right")
        for row in usage.by_model:
            c = (
                f"${row.cost_usd:.6f}"
                if row.cost_usd is not None
                else "unknown"
            )
            if row.cost_is_partial:
                c += "*"
            table.add_row(
                f"{row.provider}/{row.model}",
                str(row.calls),
                str(row.input_tokens),
                str(row.output_tokens),
                c,
            )
        console.print(table)


@prices_app.command("set")
def prices_set(
    provider: str = typer.Argument(...),
    model: str = typer.Argument(...),
    input_price: float = typer.Option(..., "--input", help="USD per 1M input tokens"),
    output_price: float = typer.Option(..., "--output", help="USD per 1M output tokens"),
    cache_read: Optional[float] = typer.Option(
        None, "--cache-read", help="USD per 1M cache-read tokens"
    ),
    cache_creation: Optional[float] = typer.Option(
        None, "--cache-creation", help="USD per 1M cache-creation tokens"
    ),
    ledger_dir: Path = typer.Option(None, "--ledger"),
) -> None:
    root = ledger_dir or _ledger_opt()
    book = CostLedger(root)
    key = book.set_price(
        provider,
        model,
        input_price,
        output_price,
        cache_read_price_per_1m=cache_read,
        cache_creation_price_per_1m=cache_creation,
    )
    typer.echo(f"set {key}: input={input_price}/1M output={output_price}/1M")


@prices_app.command("list")
def prices_list(
    ledger_dir: Path = typer.Option(None, "--ledger"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    root = ledger_dir or _ledger_opt()
    book = CostLedger(root)
    prices = book.load_prices()
    if as_json:
        payload = {k: v.model_dump() for k, v in prices.items()}
        typer.echo(json_dumps(payload))
        return
    if not prices:
        console.print("(no prices configured)")
        return
    table = Table(title="prices")
    table.add_column("key")
    table.add_column("input/1M")
    table.add_column("output/1M")
    table.add_column("source")
    for key, entry in sorted(prices.items()):
        table.add_row(
            key,
            str(entry.input_price_per_1m),
            str(entry.output_price_per_1m),
            entry.source,
        )
    console.print(table)


def json_dumps(obj: object) -> str:
    import json

    return json.dumps(obj, indent=2, ensure_ascii=False)


def _parse_dt(value: str) -> datetime:
    if len(value) == 10 and value[4] == "-" and value[7] == "-":
        value = value + "T00:00:00+00:00"
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return as_utc(dt)


if __name__ == "__main__":
    app()
