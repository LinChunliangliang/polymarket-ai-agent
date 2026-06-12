# Polymarket AI 交易 Agent

[English](README.en.md)

自动化预测市场交易机器人，每 60 分钟扫描 Polymarket 加密领域市场，调用 DeepSeek AI 估算真实概率，在发现 >8% 错误定价时自动下注。

## 功能特性

- **AI 概率估算** — DeepSeek 分析每个市场的真实胜率
- **Kelly 公式仓位管理** — 保守的分数 Kelly 控制下注比例
- **链上信号增强** — DefiLlama TVL、GitHub 活跃度、Etherscan 大户动向
- **风控保护** — 日亏损上限、单笔仓位上限、优雅停止
- **Web 面板** — 实时查看投资组合和下注历史（端口 8080）
- **Telegram 通知** — 下注、结算、触达风控上限时推送消息

## 环境要求

- Python 3.11+
- Polygon 链钱包，需持有 USDC（主网 chain_id: 137）
- [DeepSeek API Key](https://platform.deepseek.com)
- Telegram Bot Token（可选，用于通知）

## 快速开始

### 1. 克隆并初始化（VPS）

```bash
git clone https://github.com/LinChunliangliang/polymarket-ai-agent.git
cd polymarket-ai-agent
git checkout 002-polymarket-ai-agent
bash deploy/setup.sh
```

### 2. 编辑配置

```bash
nano config.yaml
```

必填项：

```yaml
polymarket:
  private_key: "0x..."     # Polygon 钱包私钥
  chain_id: 137            # 137 = 主网，80002 = 沙盒测试

deepseek:
  api_key: "sk-..."        # DeepSeek API Key

risk:
  starting_balance_usd: 50  # 起始资金（与实际充值金额一致）
  min_bet_usd: 1.0
  max_position_pct: 0.10
  daily_loss_limit_usd: 15.0

notify:
  telegram_bot_token: "..."
  telegram_chat_id: "..."
```

### 3. 检查连通性

```bash
bash deploy/start.sh check
```

### 4. 启动服务

```bash
bash deploy/start.sh
```

Web 面板：`http://<你的VPS IP>:8080`

## CLI 命令

```bash
.venv/bin/python3 cli.py check              # 检查所有 API 连通性
.venv/bin/python3 cli.py start              # 启动 Agent（真实下单）
.venv/bin/python3 cli.py start --dry-run    # 启动 Agent（只分析，不下单）
.venv/bin/python3 cli.py stop               # 优雅停止
.venv/bin/python3 cli.py status             # 查看投资组合状态
.venv/bin/python3 cli.py bets               # 查看下注历史
.venv/bin/python3 cli.py scan               # 单次市场扫描
.venv/bin/python3 cli.py web                # 启动 Web 面板
```

## 部署脚本

```bash
bash deploy/start.sh            # 拉取最新代码 + 重启所有服务
bash deploy/start.sh stop       # 停止所有服务
bash deploy/start.sh restart    # 重启所有服务
bash deploy/start.sh status     # 查看运行状态
bash deploy/start.sh logs       # 实时查看 Agent 日志
```

## 风控参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `deviation_threshold` | 0.08 | AI 估算与市场价格差距超过此值才下注 |
| `kelly_fraction` | 0.25 | Kelly 分数乘数（0.25 = 保守） |
| `max_position_pct` | 0.10 | 单笔下注不超过余额的 10% |
| `daily_loss_limit_usd` | 15.0 | 今日亏损超过此值自动暂停 |
| `min_bet_usd` | 1.0 | 最小下注金额 |

## 项目结构

```
cli.py                  所有命令入口
src/
  agent/
    main.py             配置加载、日志、启动引导
    scanner.py          Gamma API 市场获取
    estimator.py        DeepSeek AI 概率估算
    strategy.py         Kelly 公式仓位计算
    risk.py             下注前风控检查
    executor.py         Polymarket CLOB 下单
    scheduler.py        调度器（10分钟价格检查 + 60分钟AI扫描）
    signals.py          链上数据（DefiLlama / GitHub / Etherscan）
    reporter.py         状态报告生成
    notifier.py         Telegram 通知
    portfolio.py        余额与盈亏追踪
  models/               数据模型（Market, Bet, Signal, Portfolio）
  storage/db.py         SQLite 持久化
  web/app.py            FastAPI Web 面板
deploy/
  setup.sh              首次 VPS 初始化脚本
  start.sh              服务管理脚本
  agent.service         systemd 单元文件（可选）
```

## 免责声明

本项目仅供学习研究使用。预测市场交易存在本金损失风险，请勿投入超出承受范围的资金。
