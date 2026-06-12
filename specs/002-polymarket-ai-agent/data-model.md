# Data Model: Polymarket AI 套利 Agent

**Date**: 2026-06-11 | **Branch**: 002-polymarket-ai-agent

---

## 实体关系概览

```
Portfolio (1)
  └── Bet (N)              # 每笔下注记录
       └── Market (1)      # 对应的预测市场

Market (1)
  └── Signal (N)           # AI 估算历史（每次分析产生一条）
       └── OnchainSnapshot (0..N)  # 估算时使用的链上数据快照

RiskConfig (1)             # 全局风控参数（单例）
OperatingCost (N)          # AI/手续费等运营成本记录
```

---

## 实体详情

### Market（预测市场）

Polymarket 上的一个二元预测市场快照。

| 字段 | 类型 | 说明 |
|------|------|------|
| `condition_id` | TEXT PK | Polymarket 市场唯一标识 |
| `question` | TEXT | 市场问题描述（原文） |
| `category` | TEXT | 类别，本系统仅处理 "crypto" |
| `yes_price` | REAL | 当前 YES token 价格（0~1，代表概率） |
| `no_price` | REAL | 当前 NO token 价格（= 1 - yes_price） |
| `volume_usd` | REAL | 24h 交易量（美元），用于流动性过滤 |
| `liquidity_usd` | REAL | 当前订单簿深度（美元） |
| `end_datetime` | DATETIME | 市场结算截止时间 |
| `last_fetched_at` | DATETIME | 最近一次价格拉取时间 |
| `is_active` | BOOLEAN | 是否处于可交易状态 |

**验证规则**:
- `yes_price` ∈ (0.01, 0.99)：过滤已接近确定结果的市场
- `liquidity_usd` ≥ 下注金额 × 3：确保不造成明显滑点
- `end_datetime` > 当前时间 + 24h：避免临近结算的市场

**状态转换**:
```
active → settling（接近截止时间）→ resolved（已结算）
```

---

### Signal（AI 分析信号）

一次 AI 对某市场的概率估算结果。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 自增主键 |
| `condition_id` | TEXT FK | 关联的市场 |
| `estimated_prob` | REAL | AI 估算的 YES 概率（0~1） |
| `market_price` | REAL | 估算时市场的 YES 价格 |
| `deviation` | REAL | `estimated_prob - market_price`（正值=市场低估） |
| `confidence` | TEXT | "high" / "medium" / "low"（AI 自评置信度） |
| `onchain_used` | BOOLEAN | 本次估算是否使用了链上数据 |
| `ai_tokens_used` | INTEGER | 本次调用消耗的 token 数 |
| `ai_cost_usd` | REAL | 本次调用的美元成本 |
| `created_at` | DATETIME | 估算时间 |

**验证规则**:
- `estimated_prob` ∈ (0, 1)：拒绝 0 或 1 的极端值
- `|deviation|` > 0.08 才生成下注信号

---

### Bet（下注记录）

系统执行的每一笔 Polymarket 交易。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 自增主键 |
| `condition_id` | TEXT FK | 关联的市场 |
| `signal_id` | INTEGER FK | 触发本次下注的信号 |
| `side` | TEXT | "YES" 或 "NO" |
| `amount_usd` | REAL | 下注金额（美元） |
| `price_at_order` | REAL | 下单时的 token 价格 |
| `kelly_fraction` | REAL | Kelly 公式计算的原始比例 |
| `order_id` | TEXT | Polymarket 返回的订单 ID |
| `status` | TEXT | "pending" / "filled" / "cancelled" / "won" / "lost" |
| `pnl_usd` | REAL | 结算后盈亏（未结算为 NULL） |
| `created_at` | DATETIME | 下单时间 |
| `settled_at` | DATETIME | 结算时间（NULL 表示未结算） |

**状态转换**:
```
pending → filled（成交）→ won / lost（市场结算后）
pending → cancelled（下单失败或流动性不足）
```

---

### OnchainSnapshot（链上数据快照）

一次链上数据抓取的结果，关联到具体的 Signal。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 自增主键 |
| `signal_id` | INTEGER FK | 关联的分析信号 |
| `project_name` | TEXT | 相关项目名称（从市场描述中提取） |
| `tvl_usd` | REAL | 当前 TVL（DefiLlama，NULL 表示未找到） |
| `tvl_7d_change_pct` | REAL | 7 天 TVL 变化百分比 |
| `github_commits_30d` | INTEGER | 近 30 天 GitHub 提交次数（NULL 表示无数据） |
| `large_transfers_24h` | INTEGER | 近 24h 大额转账笔数（>$100K） |
| `data_sources` | TEXT | JSON 列表，记录本次使用的数据源 |
| `fetch_errors` | TEXT | JSON 列表，记录获取失败的数据源 |
| `created_at` | DATETIME | 数据抓取时间 |

---

### Portfolio（资金状态）

全局单例，记录系统整体资金状况。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 永远为 1（单例） |
| `starting_balance_usd` | REAL | 起始资金（默认 500） |
| `current_balance_usd` | REAL | 当前可用余额 |
| `total_wagered_usd` | REAL | 累计下注总额 |
| `total_ai_cost_usd` | REAL | 累计 AI API 费用 |
| `total_pnl_usd` | REAL | 累计净盈亏（已结算） |
| `daily_loss_usd` | REAL | 当日累计亏损（每日0点重置） |
| `last_updated_at` | DATETIME | 最近更新时间 |

---

### RiskConfig（风控配置）

用户可调的风控参数，存储于 `config.yaml`，启动时加载。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `max_position_pct` | REAL | 0.06 | 单笔最大下注占余额比例（6%） |
| `daily_loss_limit_usd` | REAL | 75 | 每日最大亏损额（美元） |
| `min_bet_usd` | REAL | 5 | 最小下注金额（低于此值跳过） |
| `deviation_threshold` | REAL | 0.08 | 触发下注的最小偏差（8%） |
| `min_liquidity_multiple` | REAL | 3.0 | 市场流动性须为下注额的 N 倍 |
| `kelly_fraction` | REAL | 0.25 | 分数 Kelly（保守系数，0.25 = 1/4 Kelly） |
| `ai_scan_interval_min` | INTEGER | 60 | AI 全量扫描间隔（分钟） |
| `price_check_interval_min` | INTEGER | 10 | 快速价格检查间隔（分钟） |

---

### OperatingCost（运营成本记录）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 自增主键 |
| `cost_type` | TEXT | "ai_inference" / "tx_fee" |
| `amount_usd` | REAL | 费用金额 |
| `description` | TEXT | 备注（如 "DeepSeek V4-Flash, 50 markets scan"） |
| `created_at` | DATETIME | 产生时间 |
