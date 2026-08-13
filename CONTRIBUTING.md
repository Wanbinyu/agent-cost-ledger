# Contributing

Keep the product a ledger, not a second chat client.

## Principles

1. **Never invent $0** — missing usage or prices must stay unknown/partial.
2. **Honor provided `cost_usd`** when unit prices are missing.
3. **Chat UI is optional** — `pip install '.[web]'` and `cost-ledger ui` only.
4. **Do not intercept Claude Code** — ingest transcripts; do not proxy requests.

## Dev setup

```bash
python -m pip install -e ".[test]"
python -m pytest -q
```

## Release checklist

1. `pytest -q` green on 3.11+
2. Bump `pyproject.toml` and `src/agent_cost_ledger/version.py`
3. Update CHANGELOG
4. Tag `vX.Y.Z` after push
