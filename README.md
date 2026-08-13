# agent-cost-ledger

**Token / 费用真账。** 缺单价或缺 usage 不会假装 `$0`。  
独立账本 CLI，**不是** Claude Code 插件，也不会截获 CC 流量。

[![CI](https://github.com/Wanbinyu/agent-cost-ledger/actions/workflows/ci.yml/badge.svg)](https://github.com/Wanbinyu/agent-cost-ledger/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB)
![Status](https://img.shields.io/badge/status-v0.3.2-blue)

---

## Install

Requires **Python 3.11+** and [pipx](https://pipx.pypa.io/).

```bash
pipx install git+https://github.com/Wanbinyu/agent-cost-ledger.git@v0.3.2
cost-ledger --version
```

From a clone (development):

```bash
git clone https://github.com/Wanbinyu/agent-cost-ledger.git
cd agent-cost-ledger
python -m pip install -e ".[test]"
```

---

## Use (after install, no clone needed)

```bash
cost-ledger demo
```

`demo` 写入临时账本并打印报表（不需要 API Key）。

日常记账：

```bash
# 手记一条
cost-ledger add -p openai -m gpt-4o-mini -i 100 -o 50 \
  --input-price-per-1m 0.15 --output-price-per-1m 0.6

# 看汇总（无子命令也是 report）
cost-ledger
cost-ledger report --json
```

若你用 Claude Code，会话在 `~/.claude/projects/<编码后的 cwd>/*.jsonl`：

```bash
cost-ledger ingest-cc
cost-ledger ingest-cc ~/.claude/projects/<slug>
cost-ledger report
```

| 命令 | 作用 |
|------|------|
| `cost-ledger` / `cost-ledger report` | 聚合当前目录 `.cost-ledger/` |
| `cost-ledger demo` | 跑内置样例 |
| `cost-ledger ingest-cc [path]` | 读 CC `message.usage` |
| `cost-ledger ingest events.jsonl` | 读本账本事件格式 |
| `cost-ledger add -p … -m … -i … -o …` | 手记一条 |
| `cost-ledger prices set …` | 单价表 `$/1M` |
| `cost-ledger ui` | 可选调试聊天（需 `[web]` extra） |

完成是否可信请用 [agent-audit-gate](https://github.com/Wanbinyu/agent-audit-gate)，不要用这个账本。

---

## 费用语义

- 有单价：`(in/1M)*input + (out/1M)*output`，cache 有价则另加。
- 事件自带 `cost_usd` 且没有单价：保留该总额。
- provider 没返回 usage：`usage_missing`，**不算成 $0**。
- cache token 有量无价：计入已知部分并标 `partial`。

---

## 可选调试 UI

```bash
pipx inject agent-cost-ledger 'agent-cost-ledger[web]'
# 或: python -m pip install "agent-cost-ledger[web] @ git+https://github.com/Wanbinyu/agent-cost-ledger.git@v0.3.2"
cost-ledger ui --no-open
```

浏览器打开 `http://127.0.0.1:8765/`。这是旁路聊天，不是 Claude Code。

环境变量：`OPENAI_API_KEY` 或 `COST_LEDGER_API_KEY`，以及 `OPENAI_BASE_URL` / `OPENAI_MODEL`。

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

**0.3.2** — `cost-ledger demo` 安装后即可用；文档去掉本机路径。

## License

MIT
