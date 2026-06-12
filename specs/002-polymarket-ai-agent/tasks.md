# Tasks: Polymarket AI 套利 Agent

**Input**: Design documents from `specs/002-polymarket-ai-agent/`

**Prerequisites**: plan.md ✓ | spec.md ✓ | research.md ✓ | data-model.md ✓ | contracts/ ✓ | quickstart.md ✓

**Organization**: Tasks grouped by user story — each story is independently implementable and testable.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no shared dependencies)
- **[US#]**: User story this task belongs to
- No story label = Setup or Foundational phase

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization, directory structure, configuration scaffolding.

- [X] T001 Create project directory structure: `src/agent/`, `src/models/`, `src/storage/`, `tests/unit/`, `tests/integration/`, `tests/contract/`, `logs/`, `deploy/`
- [X] T002 Create `requirements.txt` with all dependencies: `polymarket-apis`, `openai`, `httpx[asyncio]`, `apscheduler`, `pydantic`, `PyYAML`, `pytest`, `pytest-asyncio`
- [X] T003 [P] Create `config.example.yaml` per `specs/002-polymarket-ai-agent/contracts/config-schema.md` (all fields with comments, no real keys)
- [X] T004 [P] Create `.gitignore` excluding `config.yaml`, `agent.db`, `logs/`, `.env`, `*.pid`
- [X] T005 [P] Create `deploy/agent.service` systemd unit template with placeholder paths and `EnvironmentFile` directive
- [X] T006 Create `src/agent/__init__.py`, `src/models/__init__.py`, `src/storage/__init__.py` (empty init files)

**Checkpoint**: Directory structure exists, `pip install -r requirements.txt` succeeds.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure every user story depends on — SQLite schema, data models, config loading, logging.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T007 Implement config loading in `src/agent/main.py`: load `config.yaml`, apply env var overrides (`POLY_PRIVATE_KEY`, `DEEPSEEK_API_KEY`), validate with Pydantic `RiskConfig` model
- [X] T008 Implement SQLite initialization in `src/storage/db.py`: create tables for `markets`, `signals`, `bets`, `portfolio`, `operating_costs`, `onchain_snapshots` per `specs/002-polymarket-ai-agent/data-model.md`
- [X] T009 [P] Implement `Market` model in `src/models/market.py`: fields per data-model.md, validation rules (yes_price ∈ 0.01–0.99, liquidity check)
- [X] T010 [P] Implement `Signal` model in `src/models/signal.py`: fields per data-model.md including `estimated_prob`, `deviation`, `confidence`, `ai_cost_usd`
- [X] T011 [P] Implement `Bet` model in `src/models/bet.py`: fields per data-model.md, state transitions `pending → filled → won/lost/cancelled`
- [X] T012 [P] Implement `Portfolio` and `RiskConfig` models in `src/models/portfolio.py`: fields per data-model.md, defaults (`max_position_pct=0.06`, `daily_loss_limit_usd=75`, `min_bet_usd=5`)
- [X] T013 [P] Implement `OnchainSnapshot` and `OperatingCost` models in `src/models/signal.py`
- [X] T014 Implement CRUD operations in `src/storage/db.py`: `upsert_market`, `insert_signal`, `insert_bet`, `update_bet_status`, `get_portfolio`, `update_portfolio`, `insert_cost`
- [X] T015 Implement structured JSON logging in `src/agent/main.py`: log rotation (`max_size_mb`, `backup_count` from config), log level from config

**Checkpoint**: `python -c "from src.storage.db import init_db; init_db()"` creates `agent.db` with all tables.

---

## Phase 3: User Story 1 - Agent 自动发现并执行错误定价机会 (Priority: P1) 🎯 MVP

**Goal**: 系统每轮自动扫描市场 → AI 估算概率 → 发现偏差 → 计算仓位 → 在 Polymarket 沙盒完成真实下单。

**Independent Test**: 启动 Agent (`--dry-run=false`，沙盒模式) → 等待一个 AI 全扫周期 → `agent bets` 显示至少一笔 `status=filled` 记录，或日志显示"本轮无机会"。

### Implementation for User Story 1

- [X] T016 [P] [US1] Implement Polymarket client in `src/agent/scanner.py`: connect to sandbox (`chain_id=80002`), authenticate with private key, fetch all active markets
- [X] T017 [P] [US1] Implement DeepSeek client wrapper in `src/agent/estimator.py`: init `openai.AsyncOpenAI` with `base_url="https://api.deepseek.com/v1"`, basic chat completions call, JSON response parsing per `specs/002-polymarket-ai-agent/contracts/ai-prompt.md`
- [X] T018 [US1] Implement market filtering in `src/agent/scanner.py`: filter by category=crypto, yes_price ∈ (0.01, 0.99), end_date > now+24h, liquidity ≥ min_bet×3; sort by liquidity desc; take top 50
- [X] T019 [US1] Implement prompt builder in `src/agent/estimator.py`: build system prompt (fixed, cacheable) + user prompt with market fields per `contracts/ai-prompt.md`; handle `onchain_signals.available=false` path (no onchain data yet)
- [X] T020 [US1] Implement Kelly formula in `src/agent/strategy.py`: `f* = (p*b - q) / b`, apply `kelly_fraction` multiplier, cap at `max_position_pct`, return 0 if f* ≤ 0
- [X] T021 [US1] Implement basic risk checks in `src/agent/risk.py`: verify `current_balance ≥ min_bet_usd`, verify `bet_amount ≤ current_balance × max_position_pct`, return `RiskCheckResult` with pass/fail reason
- [X] T022 [US1] Implement Polymarket order placement in `src/agent/executor.py`: submit limit order to CLOB, poll for fill status (max 30s), return order result; handle `cancelled` status
- [X] T023 [US1] Implement portfolio balance update in `src/agent/portfolio.py`: deduct filled bet amount from `current_balance`, increment `total_wagered_usd`, persist to SQLite
- [X] T024 [US1] Implement bet settlement poller in `src/agent/executor.py`: query Polymarket for resolved markets, update `bet.status` to `won`/`lost`, calculate and store `pnl_usd`, update portfolio
- [X] T025 [US1] Implement AI full scan cycle in `src/agent/scheduler.py`: fetch markets → parallel DeepSeek analysis (asyncio.gather) → filter signals (deviation > threshold) → risk check → execute orders → log summary
- [X] T026 [US1] Implement price check cycle in `src/agent/scheduler.py`: fetch current prices for all tracked markets, compare to last AI estimate, flag markets where price moved >3% for priority re-analysis
- [X] T027 [US1] Implement APScheduler setup in `src/agent/main.py`: register price_check job (every 10 min) and ai_scan job (every 60 min), handle startup, write PID to `agent.pid`
- [X] T028 [US1] Implement `agent start` CLI command in `cli.py`: load config, init DB, start scheduler, per `specs/002-polymarket-ai-agent/contracts/cli.md`
- [X] T029 [US1] Implement `agent check` CLI command in `cli.py`: verify Polymarket connectivity, DeepSeek API, DefiLlama, GitHub API; print ✓/✗ per service per quickstart.md Phase 1

**Checkpoint**: `agent check` 全绿；沙盒模式运行一个完整循环后 `agent bets` 有记录。

---

## Phase 4: User Story 2 - 链上信号增强判断准确性 (Priority: P2)

**Goal**: AI 估算时能获取相关项目的 TVL 变化、GitHub 活跃度、大额转账数据，并在分析日志中可见。

**Independent Test**: 对包含已知项目名（如 Ethereum、Uniswap）的市场运行 `agent analyze --market-id <id> --verbose`，日志中出现链上数据字段且 `onchain_used=true`。

### Implementation for User Story 2

- [X] T030 [P] [US2] Implement DefiLlama TVL fetcher in `src/agent/signals.py`: `GET https://api.defillama.com/api/tvl/{protocol}` and history endpoint; return `tvl_usd` and `tvl_7d_change_pct`
- [X] T031 [P] [US2] Implement GitHub commits fetcher in `src/agent/signals.py`: `GET /repos/{owner}/{repo}/commits` with date filter; return `commits_30d`; use `GITHUB_TOKEN` from config if available
- [X] T032 [P] [US2] Implement Etherscan large transfer fetcher in `src/agent/signals.py`: query token transfer events >$100K in last 24h; return count; gracefully skip if no `ETHERSCAN_API_KEY`
- [X] T033 [US2] Implement project name extractor in `src/agent/signals.py`: regex + keyword list to identify crypto project names from market question text (e.g. "Ethereum", "Uniswap", "Solana")
- [X] T034 [US2] Implement onchain data aggregator in `src/agent/signals.py`: `asyncio.gather` all three fetchers with timeout; populate `OnchainSnapshot`; set `available=false` and log warning if all sources fail
- [X] T035 [US2] Update prompt builder in `src/agent/estimator.py` to inject `OnchainSnapshot` data when `available=true`; apply `confidence × 0.5` penalty when `confidence="low"` per `contracts/ai-prompt.md`
- [X] T036 [US2] Persist `OnchainSnapshot` to SQLite in `src/storage/db.py`: `insert_onchain_snapshot`, link to `signal_id`
- [X] T037 [US2] Implement `agent analyze --market-id <id> [--verbose]` CLI command in `cli.py` per quickstart.md Phase 3: print estimate, deviation, onchain data used, token count, cost

**Checkpoint**: `agent analyze --market-id <id> --verbose` 显示链上数据字段；`onchain_used=true` 写入 Signal 表。

---

## Phase 5: User Story 4 - 风控保护与紧急停止 (Priority: P3)

**Goal**: 每日亏损触达上限时自动暂停；`agent stop` 优雅退出；Kelly 仓位严格不超过 6%。

**Independent Test**: `agent config set daily_loss_limit_usd 0.01` → 触发模拟亏损 → `agent status` 显示 `PAUSED`，不再执行新下单。

### Implementation for User Story 4

- [X] T038 [P] [US4] Implement daily loss limit check in `src/agent/risk.py`: compare `portfolio.daily_loss_usd` to `risk_config.daily_loss_limit_usd`; return `RiskCheckResult(blocked=True, reason="daily_loss_limit_reached")` when exceeded
- [X] T039 [P] [US4] Implement daily loss reset job in `src/agent/scheduler.py`: APScheduler cron job at 00:00 UTC, reset `portfolio.daily_loss_usd = 0.0` in SQLite
- [X] T040 [US4] Implement graceful stop via flag file in `src/agent/main.py`: check for `agent.stop` flag file at start of each cycle; if present, exit cleanly and remove flag; also handle `SIGTERM`
- [X] T041 [US4] Implement `agent stop` CLI command in `cli.py`: write `agent.stop` flag file; confirm to user per `contracts/cli.md`
- [X] T042 [US4] Integrate full risk gate into execution path in `src/agent/strategy.py`: run all risk checks (balance, daily loss, position cap) before every order; log and skip on any failure
- [X] T043 [US4] Implement `agent config show` and `agent config set <key> <value>` commands in `cli.py`: read/write `config.yaml`, validate new value type, print confirmation per `contracts/cli.md`

**Checkpoint**: 设置 `daily_loss_limit_usd=0.01` 后系统自动暂停；`agent stop` 后进程退出且无孤儿进程。

---

## Phase 6: User Story 3 - 运营监控与成本管理 (Priority: P3)

**Goal**: `agent status` 显示完整资金状况；`agent bets` 显示历史记录；AI 费用自动追踪并从余额扣除。

**Independent Test**: 执行若干交易后运行 `agent status --json`，JSON 结构符合 `contracts/cli.md`，`pnl_usd` 与实际账户一致。

### Implementation for User Story 3

- [X] T044 [P] [US3] Implement AI cost tracking in `src/agent/estimator.py`: after each API call, calculate `cost_usd = (input_tokens × price_in + output_tokens × price_out)`, write `OperatingCost` record, deduct from `portfolio.current_balance`
- [X] T045 [P] [US3] Implement portfolio status calculator in `src/agent/reporter.py`: query portfolio + open bets + today's costs; build `StatusReport` dataclass with all fields from `contracts/cli.md`
- [X] T046 [US3] Implement bet history query in `src/storage/db.py`: `get_bets(limit, status_filter)` with JOIN to markets for question text; return paginated result
- [X] T047 [US3] Implement `agent status` CLI command in `cli.py`: call `reporter.get_status()`, render text table per `contracts/cli.md`; include uptime, last scan time, last bet time
- [X] T048 [US3] Implement `agent bets` CLI command in `cli.py`: call `db.get_bets(limit, status)`, render table with columns: time | market (truncated 40 chars) | side | amount | status | pnl
- [X] T049 [US3] Implement `--json` flag for `agent status` in `cli.py`: output JSON structure per `contracts/cli.md`; use Python `json.dumps` with `indent=2`

**Checkpoint**: `agent status --json` 输出结构完整；AI 费用在 `operating_costs` 表中可查；`portfolio.current_balance` 随每次 AI 调用递减。

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: `--dry-run` 模式、测试辅助命令、部署就绪。

- [X] T050 [P] Add `--dry-run` flag support in `src/agent/executor.py`: when enabled, log order details but skip actual CLOB submission; still update Signal table
- [X] T051 [P] Implement `agent scan --once --dry-run` command in `cli.py` per quickstart.md Phase 2: single scan + print market list without starting scheduler
- [X] T052 Implement `agent force-bet --market-id <id> --side <YES|NO> --amount <n>` in `cli.py` per quickstart.md Phase 4: bypass AI, directly place order (sandbox only)
- [X] T053 Implement `agent simulate-loss --amount <n>` in `cli.py` per quickstart.md Phase 5: add to `daily_loss_usd` without actual trade (for risk limit testing)
- [X] T054 Finalize `deploy/agent.service`: set `WorkingDirectory`, `ExecStart`, `EnvironmentFile=.env`, `Restart=on-failure`; add deployment instructions to README
- [X] T055 [P] Run all 6 quickstart.md validation scenarios and confirm each passes: connectivity → market scan → single analysis → sandbox bet → risk pause → 10-min cycle

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Requires Phase 1 — **blocks all user stories**
- **Phase 3 (US1, P1)**: Requires Phase 2 — Core value, implement first
- **Phase 4 (US2, P2)**: Requires Phase 3 (shares `estimator.py`) — enhances US1
- **Phase 5 (US4, P3)**: Requires Phase 3 (extends `risk.py` and `scheduler.py`)
- **Phase 6 (US3, P3)**: Requires Phase 3 (reads bet/portfolio data); can run in parallel with Phase 5
- **Phase 7 (Polish)**: Requires Phases 3–6

### User Story Dependencies

- **US1 (P1)**: Foundational → US1 — No story dependencies
- **US2 (P2)**: US1 must exist (shares `estimator.py`) — extends, does not replace
- **US4 (P3)**: US1 must exist (extends `risk.py`, `scheduler.py`) — independently testable
- **US3 (P3)**: US1 must exist (reads bets and portfolio) — independently testable

### Within Each User Story

- Data models before services (T009–T013 before T016+)
- Client wrappers [T016, T017] can be built in parallel
- Signal detection (T025) depends on scanner (T018) and estimator (T019–T020)
- Order execution (T022) depends on risk check (T021)
- CLI commands depend on underlying services being implemented

---

## Parallel Opportunities

```bash
# Phase 2 — All model tasks can run in parallel:
T009 src/models/market.py
T010 src/models/signal.py
T011 src/models/bet.py
T012 src/models/portfolio.py
T013 src/models/signal.py (OnchainSnapshot, OperatingCost)

# Phase 3 — Client wrappers can run in parallel:
T016 src/agent/scanner.py (Polymarket client)
T017 src/agent/estimator.py (DeepSeek client)

# Phase 4 — All three data fetchers can run in parallel:
T030 DefiLlama TVL fetcher
T031 GitHub commits fetcher
T032 Etherscan transfer fetcher

# Phase 6 — Status report and cost tracking can run in parallel:
T044 AI cost tracking (estimator.py)
T045 Portfolio status calculator (reporter.py)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (~30 min)
2. Complete Phase 2: Foundational — CRITICAL (~2h)
3. Complete Phase 3: US1 (~4–6h)
4. **STOP and VALIDATE** via quickstart.md Phases 1–4
5. Run in sandbox for 24h — confirm scan cycles work and no crashes

### Incremental Delivery

| Step | What's Added | Validation |
|------|-------------|------------|
| Phase 1+2 | Foundation | `python -c "from src.storage.db import init_db; init_db()"` |
| + Phase 3 | Core trading loop | `agent check` 全绿 + sandbox bet placed |
| + Phase 4 | Onchain signals | `agent analyze --verbose` shows TVL/GitHub data |
| + Phase 5 | Full risk controls | Daily loss limit triggers correctly |
| + Phase 6 | Monitoring | `agent status --json` complete output |
| + Phase 7 | Production ready | All quickstart.md scenarios pass |

---

## Notes

- **[P]** = different files, no blocking dependencies within the phase
- **[US#]** maps to user stories in `specs/002-polymarket-ai-agent/spec.md`
- Always use **Polymarket sandbox** (`chain_id=80002`) during development — never mainnet until Phase 7
- `config.yaml` must never be committed — checked via T004 `.gitignore`
- DeepSeek API: new users have 5M free tokens — sufficient for entire development cycle
- Phase 3 is the only phase needed for a working MVP; everything else enhances or monitors it
