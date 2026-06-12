# Polymarket AI Trading Agent

An automated prediction market trading agent that scans Polymarket crypto markets every 60 minutes, uses DeepSeek AI to estimate true probabilities, and places bets when it finds mispricings greater than 8%.

## Features

- **AI-powered analysis** — DeepSeek estimates win probability for each market
- **Kelly criterion sizing** — Conservative fractional Kelly position sizing
- **On-chain signals** — DefiLlama TVL, GitHub activity, Etherscan whale transfers
- **Risk controls** — Daily loss limit, per-bet position cap, graceful stop
- **Web dashboard** — Real-time portfolio and bet history on port 8080
- **Telegram notifications** — Alerts on bets placed, settlements, and risk events

## Requirements

- Python 3.11+
- Polygon wallet with USDC (mainnet chain_id: 137)
- [DeepSeek API key](https://platform.deepseek.com)
- Telegram bot token (optional, for notifications)

## Quick Start

### 1. Clone & Setup (VPS)

```bash
git clone https://github.com/LinChunliangliang/polymarket-ai-agent.git
cd polymarket-ai-agent
git checkout 002-polymarket-ai-agent
bash deploy/setup.sh
```

### 2. Configure

```bash
nano config.yaml
```

Required fields:

```yaml
polymarket:
  private_key: "0x..."     # Polygon wallet private key
  chain_id: 137            # 137 = mainnet, 80002 = sandbox

deepseek:
  api_key: "sk-..."        # DeepSeek API key

risk:
  starting_balance_usd: 50
  min_bet_usd: 1.0
  max_position_pct: 0.10
  daily_loss_limit_usd: 15.0

notify:
  telegram_bot_token: "..."
  telegram_chat_id: "..."
```

### 3. Check Connectivity

```bash
bash deploy/start.sh check
```

### 4. Start

```bash
bash deploy/start.sh
```

Web dashboard: `http://<your-vps-ip>:8080`

## CLI Commands

```bash
.venv/bin/python3 cli.py check            # Verify all API connections
.venv/bin/python3 cli.py start            # Start agent (real orders)
.venv/bin/python3 cli.py start --dry-run  # Start without placing orders
.venv/bin/python3 cli.py stop             # Graceful stop
.venv/bin/python3 cli.py status           # Portfolio & agent status
.venv/bin/python3 cli.py bets             # Bet history
.venv/bin/python3 cli.py scan             # One-shot market scan
.venv/bin/python3 cli.py web              # Start web dashboard
```

## Deploy Scripts

```bash
bash deploy/start.sh            # Pull latest + restart all services
bash deploy/start.sh stop       # Stop all services
bash deploy/start.sh restart    # Restart all services
bash deploy/start.sh status     # Check running status
bash deploy/start.sh logs       # Tail agent logs
```

## Risk Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `deviation_threshold` | 0.08 | Min AI vs market price gap to trigger a bet |
| `kelly_fraction` | 0.25 | Fractional Kelly multiplier (conservative) |
| `max_position_pct` | 0.10 | Max % of balance per bet |
| `daily_loss_limit_usd` | 15.0 | Auto-pause threshold |
| `min_bet_usd` | 1.0 | Minimum bet size |

## Architecture

```
cli.py                  Entry point for all commands
src/
  agent/
    main.py             Config loading, logging, bootstrap
    scanner.py          Gamma API market fetcher
    estimator.py        DeepSeek AI probability estimator
    strategy.py         Kelly criterion bet sizing
    risk.py             Pre-bet risk gate
    executor.py         Polymarket CLOB order placement
    scheduler.py        APScheduler: 10min price check + 60min AI scan
    signals.py          On-chain data (DefiLlama / GitHub / Etherscan)
    reporter.py         Status report builder
    notifier.py         Telegram notifications
    portfolio.py        Balance & P&L tracking
  models/               Data models (Market, Bet, Signal, Portfolio)
  storage/db.py         SQLite persistence
  web/app.py            FastAPI dashboard
deploy/
  setup.sh              First-time VPS setup
  start.sh              Service management script
  agent.service         systemd unit (optional)
```

## ⚠️ Disclaimer

This software is for educational purposes. Prediction market trading involves substantial risk of loss. Never trade with money you cannot afford to lose.
