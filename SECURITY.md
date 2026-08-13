# Security

`agent-cost-ledger` is a **local** ledger. The optional chat UI binds to
`127.0.0.1` by default.

## What to keep off the ledger

- API keys, tokens, cookies (do not put them in event `notes`)
- Customer data you cannot share

The chat UI may write a key to `.cost-ledger/settings.json` in the working
directory. That path is gitignored here; do not commit it from your project.

`--host` other than loopback exposes that local API. Prefer `127.0.0.1`.

## Supply chain

Install from a git URL or path you trust. Pin a tag in CI when possible.
