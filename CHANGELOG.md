# Changelog

## 0.3.0

### Changed

- Default `cost-ledger` (no subcommand) prints a **report**, it no longer opens a browser.
- Chat UI is optional: `pip install 'agent-cost-ledger[web]'` then `cost-ledger ui`.
- `usage-chat` still launches the UI (backward compatible).
- FastAPI / uvicorn / httpx moved to the `[web]` extra.

### Fixed

- Missing provider `usage` no longer becomes a complete `$0` bill.
- Precomputed `cost_usd` is kept when unit prices are missing.
- `--since` / `--until` without a timezone no longer crash.

### Added

- `cost-ledger ingest-cc` — ingest Claude Code project JSONL (`message.usage`, cache tokens).
- Cache-read / cache-creation token fields and optional prices.

## 0.2.0

### Added

- **Chat UI** with bottom **usage bar** (session + total tokens/cost)
- Default command: bare `cost-ledger` / `usage-chat` launches UI and opens browser
- Auto-append ledger events after each chat turn (no manual `add`)
- One-time setup panel or env-based zero-prompt config
- Package data: HTML/CSS/JS
- Tests for webapp settings + auto ledger

### Notes

- OpenAI-compatible `/chat/completions` only in this version
- Does not intercept Claude Code traffic

## 0.1.0

- JSONL ledger, prices, add/ingest/report CLI
