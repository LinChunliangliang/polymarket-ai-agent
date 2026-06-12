# Quickstart & Validation Guide

**Branch**: 002-polymarket-ai-agent

端到端验证指南，用于确认系统各模块按预期工作。

---

## 前置条件

- Python 3.11+
- Polygon 测试网钱包（带 USDC，通过 Polymarket 沙盒水龙头获取）
- DeepSeek API Key（新用户有 5M 免费 token）
- GitHub Personal Access Token（可选，提升链上数据质量）

---

## 阶段 1：环境验证

**目标**：确认依赖安装、配置加载、外部 API 均可连通。

```bash
# 安装依赖
pip install -r requirements.txt

# 复制配置模板
cp config.example.yaml config.yaml
# 编辑 config.yaml，填入沙盒私钥和 DeepSeek API Key

# 验证配置和连通性
python -m agent check

# 预期输出：
# ✓ Config loaded
# ✓ Polymarket sandbox connected (balance: 1000.00 USDC)
# ✓ DeepSeek API reachable (model: deepseek-chat)
# ✓ DefiLlama API reachable
# ✓ GitHub API reachable (rate limit: 30/min)
# ✓ Etherscan API reachable
```

**验证通过条件**：所有条目显示 ✓

---

## 阶段 2：市场扫描验证

**目标**：确认系统能正确拉取 Polymarket 加密类市场并过滤。

```bash
python -m agent scan --once --dry-run

# 预期输出：
# Fetched 87 active crypto markets
# After liquidity filter (>$100 depth): 52 markets
# Sample market: "Will BTC exceed $120K before Jul 1?" | YES: 0.34 | Liquidity: $4,200
```

**验证通过条件**：成功拉取 >10 个市场，价格格式正确（0~1 之间）

---

## 阶段 3：AI 估算验证（单市场）

**目标**：确认 DeepSeek 可返回合法概率估算。

```bash
python -m agent analyze --market-id <condition_id_from_above> --verbose

# 预期输出：
# Market: "Will BTC exceed $120K before Jul 1?"
# Current price: YES 0.34
# Onchain data: TVL N/A | GitHub: N/A (no project match)
# DeepSeek estimate: 0.41 (confidence: medium)
# Deviation: +0.07 (below 0.08 threshold, no signal)
# Tokens used: 712 | Cost: $0.0001
```

**验证通过条件**：返回 0~1 之间的概率，`confidence` 字段存在，Token 用量有记录

---

## 阶段 4：信号触发与沙盒下单验证

**目标**：确认偏差 >8% 时系统正确计算 Kelly 仓位并在沙盒下单。

```bash
# 方法1：等待自然信号（可能需要多次扫描）
python -m agent start --dry-run=false  # 沙盒模式，使用测试 USDC

# 方法2：手动触发（测试用）
python -m agent force-bet --market-id <id> --side YES --amount 10

# 验证下单成功
python -m agent bets --limit 5

# 预期输出（含一笔 status=filled 的记录）：
# 2026-06-11 14:22  Will BTC exceed $120K...  YES  $10.00  FILLED
```

**验证通过条件**：Polymarket 沙盒账户中出现对应仓位，`agent bets` 显示 status=filled

---

## 阶段 5：风控验证

**目标**：确认每日亏损限额触发时系统自动停止。

```bash
# 临时将 daily_loss_limit_usd 改为极小值（测试用）
python -m agent config set daily_loss_limit_usd 0.01

# 触发一笔亏损（在沙盒中手动结算一个 NO 的市场）
# 或直接模拟：
python -m agent simulate-loss --amount 1

# 验证 Agent 停止
python -m agent status

# 预期输出：
# Status: PAUSED (daily loss limit reached: $0.01 / $0.01)
# No new bets will be placed until manually resumed.
```

**验证通过条件**：Agent 状态变为 PAUSED，不再执行新交易

---

## 阶段 6：完整 10 分钟循环验证

**目标**：确认调度器按时触发，两阶段扫描均正常运行。

```bash
python -m agent start

# 等待 10 分钟，查看日志
tail -f logs/agent.log | grep "cycle"

# 预期日志：
# [14:00:00] price_check_cycle started | markets: 87 | duration: 3.2s
# [14:10:00] price_check_cycle started | markets: 87 | duration: 2.8s
# [15:00:00] ai_scan_cycle started | markets_to_analyze: 50
# [15:01:42] ai_scan_cycle completed | signals_found: 3 | bets_placed: 1 | ai_cost: $0.008
```

**验证通过条件**：
- 每 10 分钟出现 `price_check_cycle` 日志
- 每 60 分钟出现 `ai_scan_cycle` 日志
- AI 费用被记录且 >0

---

## 已知限制（非阻塞）

- 代币解锁数据目前无免费 API，AI 估算时该字段缺失，标注为低置信度
- Etherscan 免费版限速 3 req/s，高频扫描时部分链上数据可能延迟
- Polymarket 沙盒市场数量远少于主网（约 10-20 个 vs 主网 500+），AI 信号频率会偏低
