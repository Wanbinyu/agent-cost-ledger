# agent-cost-ledger

> **Claude Code 日常用量请用**  
> [`G:\skill\cc-usage-gate`](../cc-usage-gate)（底栏官方 cost + 工具审计）。  
> 本仓库是**独立账本**：ingest / report。聊天 UI 只是可选调试，**不是** CC 插件，也**不会**截获 Claude Code 流量。

**Token / 费用真账。** 缺单价或缺 usage 不会假装 `$0`。

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB)
![Status](https://img.shields.io/badge/status-v0.3.0-blue)

---

## 别人怎么直接用

```bash
pipx install G:\skill\agent-cost-ledger
# 或: python -m pip install -e G:\skill\agent-cost-ledger

# 无子命令 = 报表
cost-ledger

# 从 Claude Code 项目记录记账
cost-ledger ingest-cc
cost-ledger ingest-cc ~/.claude/projects/<slug>
cost-ledger report --json
```

| 命令 | 作用 |
|------|------|
| `cost-ledger` / `cost-ledger report` | 聚合本目录 `.cost-ledger/` |
| `cost-ledger ingest-cc [path]` | 读 CC `*.jsonl` 里的 `message.usage` |
| `cost-ledger ingest events.jsonl` | 读本账本自己的事件格式 |
| `cost-ledger add -p … -m … -i … -o …` | 手记一条 |
| `cost-ledger prices set …` | 单价表 `$/1M` |
| `cost-ledger ui` | 可选调试聊天（需 `[web]` extra） |

---

## Claude Code → 账本

1. 正常用 Claude Code。会话写在 `~/.claude/projects/<编码后的 cwd>/*.jsonl`。
2. 在项目目录跑 `cost-ledger ingest-cc`（省略路径则按当前目录找）。
3. `cost-ledger report` 看本会话/累计 token。有官方 `cost_usd` 会保留；否则按单价表算，缺价显示 `unknown` / `*`。

完成是否可信请用 **agent-audit-gate** / **cc-usage-gate**，不要用这个账本。

---

## 费用语义

- 有单价：`(in/1M)*input + (out/1M)*output`，cache 有价则另加。
- 事件自带 `cost_usd` 且没有单价：保留该总额。
- provider 没返回 usage：`usage_missing`，**不算成 $0**。
- cache token 有量无价：计入已知部分并标 `partial`。

---

## 可选调试 UI

```bash
python -m pip install -e "G:\skill\agent-cost-ledger[web]"
cost-ledger ui --no-open
```

浏览器打开 `http://127.0.0.1:8765/`。这是旁路聊天，不是 Claude Code。

环境变量（UI / 兼容接口）：`OPENAI_API_KEY` 或 `COST_LEDGER_API_KEY`，以及 `OPENAI_BASE_URL` / `OPENAI_MODEL`。

---

## 隐私

- 账本在当前目录 `.cost-ledger/`
- UI 默认只监听 `127.0.0.1`
- 无遥测、无上传

---

## 开发

```bash
python -m pip install -e ".[test]"
python -m pytest -q
```

## 版本

**0.3.0** — 默认 report；`ingest-cc`；缺 usage 不再装 $0；Web 改为 extra。

## License

MIT
