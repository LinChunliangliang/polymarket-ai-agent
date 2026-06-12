# Implementation Plan: Polymarket AI 套利 Agent

**Branch**: `002-polymarket-ai-agent` | **Date**: 2026-06-11 | **Spec**: [spec.md](spec.md)

---

## Summary

构建一个 Python 异步服务，每 10 分钟快速检查 Polymarket 加密类预测市场价格变化，每 60 分钟调用 DeepSeek API 对前 50 个流动性最高的市场进行概率估算，结合 DefiLlama/GitHub/Etherscan 链上信号增强判断准确性，当估算偏差超过 8% 时用 Kelly 公式计算仓位并自动执行下单。系统以 SQLite 持久化状态，部署为 Linux systemd 服务。

---

## Technical Context

**Language/Version**: Python 3.11

**Primary Dependencies**:
- `polymarket-apis` — 官方 Polymarket CLOB 客户端
- `openai` — DeepSeek API（OpenAI 兼容接口）
- `httpx[asyncio]` — 异步 HTTP 请求（DefiLlama、GitHub、Etherscan）
- `apscheduler` — 任务调度（10min / 60min 双周期）
- `pydantic` — 数据模型和配置校验
- `PyYAML` — 配置文件解析

**Storage**: SQLite（内置，零运维）

**Testing**: pytest + pytest-asyncio

**Target Platform**: Ubuntu 22.04 LTS VPS（$4-6/月）

**Performance Goals**:
- 快扫周期 < 10s（仅价格拉取）
- AI 全扫周期 < 3min（50 个市场并行分析）
- 下单到成交确认 < 5s

**Constraints**:
- AI 推理成本 < $0.50/天（DeepSeek V4-Flash + Context Caching）
- 内存占用 < 256MB（低配 VPS 兼容）
- 无外部数据库依赖

**Scale/Scope**: 单用户单账户，最多同时持有 20 个未结算头寸

---

## Constitution Check

无有效 Constitution 约束（模板未填写），跳过 Gate 检查。

---

## Project Structure

```text
src/
├── agent/
│   ├── __init__.py
│   ├── main.py           # 程序入口，初始化 + 启动调度器
│   ├── scheduler.py      # 双周期任务调度（快扫 + AI 全扫）
│   ├── scanner.py        # Polymarket 市场拉取和过滤
│   ├── signals.py        # 链上数据抓取（DefiLlama / GitHub / Etherscan）
│   ├── estimator.py      # DeepSeek 概率估算（含 prompt 构建和响应解析）
│   ├── strategy.py       # Kelly 公式 + 信号过滤 + 下注决策
│   ├── executor.py       # Polymarket 下单 + 订单状态跟踪
│   ├── portfolio.py      # 资金状态管理 + 成本记录
│   ├── risk.py           # 风控检查（单笔上限 / 每日亏损限额）
│   └── reporter.py       # 状态报告生成
├── models/
│   ├── market.py         # Market 数据模型
│   ├── signal.py         # Signal + OnchainSnapshot 数据模型
│   ├── bet.py            # Bet 数据模型
│   └── portfolio.py      # Portfolio + RiskConfig 数据模型
└── storage/
    └── db.py             # SQLite CRUD 操作

cli.py                    # CLI 入口（start/stop/status/bets/config/analyze）
config.example.yaml       # 配置模板（提交到版本控制）
config.yaml               # 实际配置（.gitignore 忽略）
requirements.txt
.env.example

tests/
├── unit/
│   ├── test_strategy.py     # Kelly 公式、信号过滤逻辑
│   ├── test_estimator.py    # Prompt 构建、响应解析
│   └── test_risk.py         # 风控边界条件
├── integration/
│   ├── test_scanner.py      # Polymarket sandbox 市场拉取
│   └── test_signals.py      # DefiLlama / GitHub API 真实调用
└── contract/
    └── test_ai_output.py    # DeepSeek 输出格式校验

logs/                     # 运行日志（.gitignore 忽略）
agent.db                  # SQLite 数据库（.gitignore 忽略）
agent.pid                 # 进程 PID 文件
deploy/
└── agent.service         # systemd service 模板
```

---

## Implementation Phases

### Phase 1 — 基础框架（核心可运行）

目标：`python -m agent check` 和 `python -m agent scan --once --dry-run` 可正常工作。

1. 项目结构和依赖安装（`requirements.txt`、虚拟环境）
2. 配置加载（`config.yaml` 解析，环境变量覆盖，Pydantic 校验）
3. SQLite 初始化（建表：markets、signals、bets、portfolio、operating_costs）
4. Polymarket 市场拉取（`scanner.py`：获取加密类市场，解析价格和流动性）
5. CLI 骨架（`start / stop / status / check` 命令）

**验收**: `agent check` 全绿，`agent scan --once --dry-run` 输出市场列表

---

### Phase 2 — AI 估算引擎

目标：`python -m agent analyze --market-id <id>` 返回合法概率估算。

1. DeepSeek 客户端封装（`estimator.py`：构建 prompt、解析 JSON 输出、错误重试）
2. 链上数据抓取（`signals.py`：DefiLlama TVL、GitHub commits、Etherscan 转账）
3. 项目名称提取（从市场描述中识别加密项目关键词）
4. 信号聚合（将链上数据注入 prompt context）
5. 估算结果写入 SQLite（Signal 表）
6. AI 成本追踪（OperatingCost 表）

**验收**: 单市场分析返回合法 JSON，token 用量和成本被记录

---

### Phase 3 — 下单执行与风控

目标：发现偏差 >8% 的市场，在沙盒中完成真实下单。

1. Kelly 仓位计算（`strategy.py`：公式实现、分数 Kelly、上限截断）
2. 风控检查（`risk.py`：单笔上限、每日亏损、最小金额、流动性）
3. Polymarket 下单（`executor.py`：CLOB 下单、订单状态轮询、成交确认）
4. 投资组合状态更新（`portfolio.py`：余额变动、盈亏计算）
5. 头寸结算监听（定期检查已下注市场的结算状态）

**验收**: 沙盒账户出现真实仓位，`agent bets` 显示 status=filled

---

### Phase 4 — 调度器与完整循环

目标：`agent start` 后无人值守运行，日志完整，状态正确。

1. 双周期调度器（快扫 10min + AI 全扫 60min）
2. 快扫逻辑（价格变化检测，标记待重新分析的市场）
3. AI 全扫逻辑（取前 50 流动性市场，并行分析）
4. 状态报告（`agent status` 完整输出）
5. 紧急停止（`agent stop` 优雅退出）
6. 每日亏损重置（00:00 UTC 重置 `daily_loss_usd`）

**验收**: 连续运行 24 小时无崩溃，日志包含完整快扫和 AI 全扫记录

---

### Phase 5 — 部署与生产就绪

目标：可部署到真实 VPS 并切换主网。

1. systemd service 文件（`deploy/agent.service`）
2. 环境变量安全加载（私钥不写入日志）
3. 日志轮转配置（max 50MB × 7 文件）
4. 主网切换配置说明（`chain_id: 137`，真实 USDC）
5. 监控告警（余额不足、每日亏损触发发送告警，默认输出到日志，可扩展到 Telegram）

**验收**: `systemctl status polymarket-agent` 显示 active，重启后自动恢复运行
