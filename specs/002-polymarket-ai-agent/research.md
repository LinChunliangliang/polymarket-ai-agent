# Research: Polymarket AI 套利 Agent

**Date**: 2026-06-11 | **Branch**: 002-polymarket-ai-agent

---

## 1. Polymarket CLOB API

**Decision**: 使用官方 `polymarket-apis` Python 包（2026 年统一新包，替代旧 `py-clob-client`）

**关键事实**:
- 认证：两层体系 — L1 用 Polygon 钱包 EIP-712 签名换取 apiKey/secret/passphrase；L2 用 HMAC-SHA256 签名每条请求
- 抵押物：Polygon 链上的 USDC（链 ID 137），交易前需 approve ERC-1155 token
- 沙盒：`sandbox.polymarket.com`，有假 USDC 水龙头（每次 ~1000 枚），可完整测试下单流程
- 限速：REST 15,000 次/10s；POST /order 120,000 次/10min；总体宽松，不构成瓶颈
- WebSocket：支持市场价格订阅，可用于实时监听价格变化

**Alternatives considered**: 直接链上合约交互 → 复杂度高 10 倍，无必要

---

## 2. DeepSeek API

**Decision**: 使用 DeepSeek V4-Flash（`deepseek-chat` 兼容调用）作为概率估算模型

**关键事实**:
- 接口：`https://api.deepseek.com/v1`，完全兼容 OpenAI SDK（只改 base_url 和 model 名）
- 模型选择：
  - **V4-Flash**：$0.14/M 输入，$0.28/M 输出，1M token 上下文，适合批量分析
  - **V4-Pro**：$0.435/M 输入，更强推理，用于高置信度二次验证
- Context Caching：命中缓存的 token 仅 $0.0028/M（折扣 98%），系统提示词和市场背景可大量复用
- 新用户：赠送 5M 免费 token，足够前期调试

**成本估算**（每日）:
```
每轮扫描分析 50 个市场 × 800 tokens = 40,000 tokens/扫描
每小时 1 次 AI 全量扫描（10 分钟轮询为价格快扫，不调 AI）
24 次/天 × 40,000 = 960,000 tokens/天
输入成本：$0.14/M × 0.96M ≈ $0.13/天 ≈ $4/月
```

**Alternatives considered**: Claude API（更强但更贵）→ 可作后期升级选项

---

## 3. 链上数据信号

**Decision**: 组合使用 DefiLlama + GitHub API + Etherscan，不依赖付费数据

| 数据类型 | 来源 | 限制 | 用法 |
|---------|------|------|------|
| 协议 TVL / 变化 | DefiLlama API（免费无限） | 无认证，无已知限速 | 识别 TVL 异常下降 |
| 代码库活跃度 | GitHub API（认证后 30 req/min） | 需 Personal Access Token | 识别开发停滞 |
| 大额链上转账 | Etherscan API（免费 3 req/s，10万/天） | 仅 EVM 链 | 识别大户异动 |
| 代币解锁计划 | 无免费 API | TokenUnlocks.app 无公开 API | **降级处理**：从 DeepSeek 知识库推断，标注为低置信度数据 |

**Alternatives considered**: Nansen/Whale Alert（付费）→ 超出预算；链上 RPC 直接查 → 对 Solana 等非 EVM 链适用

---

## 4. 架构决策

**Decision**: Python 3.11 异步单进程服务，SQLite 持久化，systemd 守护进程

**关键选择**:

| 决策点 | 选择 | 理由 |
|-------|------|------|
| 语言 | Python 3.11 | Polymarket SDK、OpenAI SDK、DefiLlama 均有 Python 支持 |
| 存储 | SQLite | 单机部署，数据量小，零运维成本 |
| 调度 | APScheduler + asyncio | 轻量、支持异步任务 |
| AI 调用策略 | 快扫（10min）+ AI 全扫（60min）分离 | 降低 AI 成本同时保持响应速度 |
| 部署 | systemd service on Ubuntu VPS | 最简运维，$4-6/月 VPS 足够 |

**扫描策略（两阶段）**:
```
每 10 分钟：快扫
  → 拉取所有加密市场的最新价格
  → 与上次 AI 估算结果对比
  → 如果价格偏移 > 3%，标记为"待重新分析"

每 60 分钟：AI 全扫
  → 取流动性最高的 50 个加密市场
  → 并行抓取链上信号
  → 批量调用 DeepSeek 估算概率
  → 更新信号缓存，触发下单决策
```

**Alternatives considered**: 每 10 分钟全量 AI 扫描 → 成本 6 倍，不合理
