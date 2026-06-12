# Contract: CLI Interface

**Branch**: 002-polymarket-ai-agent

Agent 通过命令行启动和管理，所有命令输出均为人类可读文本，支持 `--json` 标志输出结构化 JSON。

---

## 命令列表

### `agent start`
启动 Agent 后台服务。

```
用法: python -m agent start [--dry-run]

选项:
  --dry-run    运行扫描和分析，但不执行真实下单（用于验证策略）

输出（成功）:
  Agent started. PID: 12345
  Config loaded: config.yaml
  Portfolio balance: $487.32
  Next AI scan in: 60 min | Next price check in: 10 min

退出码: 0=成功, 1=已在运行, 2=配置错误
```

---

### `agent stop`
发送停止信号，Agent 在当前周期结束后退出。

```
用法: python -m agent stop

输出:
  Stop signal sent. Agent will halt after current cycle.
  Current cycle: price_check (estimated 5s remaining)

退出码: 0=成功, 1=Agent 未运行
```

---

### `agent status`
显示当前运行状态和资金概况。

```
用法: python -m agent status [--json]

输出（文本）:
  ── Agent Status ───────────────────────────────
  Status:        RUNNING (PID 12345)
  Uptime:        2d 4h 31m
  Last AI scan:  2026-06-11 14:00:02 (58m ago)
  Last bet:      2026-06-11 12:33:17

  ── Portfolio ──────────────────────────────────
  Starting:      $500.00
  Current:       $523.41  (+$23.41 / +4.7%)
  Open bets:     3  ($45.20 at risk)
  AI costs:      $2.87 (total)
  Daily loss:    $8.20 / $75.00 limit

  ── Last 5 Bets ────────────────────────────────
  2026-06-11 12:33  BTC $100K by Jun 30  YES  $12.00  OPEN
  2026-06-11 08:11  ETH ETF staking Q2   YES  $18.50  WON +$9.20
  2026-06-10 22:05  Solana V3 mainnet    NO   $15.00  LOST -$15.00
  ...

输出（--json）:
{
  "status": "running",
  "pid": 12345,
  "portfolio": {
    "starting_usd": 500.00,
    "current_usd": 523.41,
    "pnl_usd": 23.41,
    "open_bets": 3,
    "daily_loss_usd": 8.20
  },
  "last_scan_at": "2026-06-11T14:00:02Z",
  "last_bet_at": "2026-06-11T12:33:17Z"
}
```

---

### `agent bets`
查看历史下注记录。

```
用法: python -m agent bets [--limit N] [--status open|closed|all] [--json]

默认: --limit 20 --status all

输出列: 时间 | 市场描述（截断至40字）| 方向 | 金额 | 状态 | 盈亏
```

---

### `agent config`
查看或修改风控参数。

```
用法:
  python -m agent config show
  python -m agent config set <key> <value>

示例:
  python -m agent config set daily_loss_limit_usd 50
  python -m agent config set deviation_threshold 0.10

输出（set 成功）:
  Updated: daily_loss_limit_usd = 50.0 (was 75.0)
  Note: Changes take effect on next scan cycle.
```
