#!/usr/bin/env python3
"""Polymarket AI Agent CLI."""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path


def cmd_check(args) -> None:
    """Verify connectivity to all external services."""
    from src.agent.main import bootstrap, get_config
    cfg = bootstrap(args.config)
    results = {}

    print("Checking connectivity...")

    # Polymarket
    try:
        import httpx
        r = httpx.get("https://gamma-api.polymarket.com/markets?limit=1&active=true", timeout=10)
        results["Polymarket"] = r.status_code == 200
    except Exception as e:
        results["Polymarket"] = False

    # DeepSeek
    try:
        from openai import OpenAI
        client = OpenAI(api_key=cfg.deepseek.api_key, base_url="https://api.deepseek.com/v1")
        client.models.list()
        results["DeepSeek API"] = True
    except Exception:
        results["DeepSeek API"] = bool(cfg.deepseek.api_key)

    # DefiLlama
    try:
        import httpx
        r = httpx.get("https://api.defillama.com/tvl/ethereum", timeout=10)
        results["DefiLlama"] = r.status_code == 200
    except Exception:
        results["DefiLlama"] = False

    # GitHub
    try:
        import httpx
        headers = {}
        if cfg.onchain.github_token:
            headers["Authorization"] = f"token {cfg.onchain.github_token}"
        r = httpx.get("https://api.github.com/rate_limit", headers=headers, timeout=10)
        data = r.json()
        limit = data.get("rate", {}).get("limit", 0)
        results[f"GitHub API (rate limit: {limit}/hr)"] = r.status_code == 200
    except Exception:
        results["GitHub API"] = False

    all_ok = True
    for service, ok in results.items():
        symbol = "✓" if ok else "✗"
        print(f"  {symbol} {service}")
        if not ok:
            all_ok = False

    from src.storage.db import get_portfolio
    portfolio = get_portfolio()
    print(f"\n  Portfolio balance: ${portfolio.current_balance_usd:.2f}")

    if not all_ok:
        sys.exit(1)


def cmd_start(args) -> None:
    """Start the agent."""
    import signal as _signal
    from src.agent.main import bootstrap, to_risk_config, write_pid, clear_stop_flag
    from src.agent.scheduler import setup_scheduler

    cfg = bootstrap(args.config)
    clear_stop_flag()
    write_pid()

    risk = to_risk_config(cfg)

    print(f"Agent starting (dry_run={args.dry_run}, chain_id={cfg.polymarket.chain_id})")
    print(f"Portfolio balance: ${__import__('src.storage.db', fromlist=['get_portfolio']).get_portfolio().current_balance_usd:.2f}")
    print(f"AI scan every {risk.ai_scan_interval_min}min | Price check every {risk.price_check_interval_min}min")

    poly_client = None
    if not args.dry_run and cfg.polymarket.private_key:
        try:
            from py_clob_client.client import ClobClient
            from py_clob_client.clob_types import ApiCreds
            host = "https://clob.polymarket.com"
            chain_id = cfg.polymarket.chain_id
            poly_client = ClobClient(host, key=cfg.polymarket.private_key, chain_id=chain_id)
            poly_client.set_api_creds(poly_client.derive_api_key())
            print("Polymarket CLOB client initialized.")
        except Exception as e:
            print(f"WARNING: Failed to init Polymarket client: {e}")
            print("Running without order placement (analysis only).")

    scheduler = setup_scheduler(risk, poly_client=poly_client, dry_run=args.dry_run)

    async def _run():
        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()

        def _handle_stop():
            print("\nStop signal received, shutting down...")
            scheduler.shutdown(wait=False)
            stop_event.set()

        loop.add_signal_handler(_signal.SIGTERM, _handle_stop)
        loop.add_signal_handler(_signal.SIGINT, _handle_stop)

        scheduler.start()
        print("Agent running. Press Ctrl+C to stop.")
        await stop_event.wait()

    try:
        asyncio.run(_run())
    finally:
        from src.agent.main import clear_pid
        clear_pid()
        print("Agent stopped.")


def cmd_stop(args) -> None:
    """Send stop signal to running agent."""
    from src.agent.main import STOP_FLAG
    STOP_FLAG.write_text("stop")
    print("Stop signal sent. Agent will halt after current cycle.")

    pid_file = Path("agent.pid")
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            print(f"Agent PID: {pid}")
        except Exception:
            pass


def cmd_status(args) -> None:
    """Show agent status and portfolio."""
    from src.agent.main import bootstrap, get_config
    from src.agent.reporter import get_status, format_status_text

    bootstrap(args.config)
    cfg = get_config()
    report = get_status(daily_loss_limit=cfg.risk.daily_loss_limit_usd)

    if args.json:
        print(json.dumps({
            "status": report.status,
            "pid": report.pid,
            "portfolio": {
                "starting_usd": report.portfolio_starting,
                "current_usd": report.portfolio_current,
                "pnl_usd": report.portfolio_pnl,
                "pnl_pct": round(report.portfolio_pnl_pct, 2),
                "open_bets": report.open_bets,
                "daily_loss_usd": report.daily_loss,
            },
            "ai_cost_total_usd": report.total_ai_cost,
            "ai_cost_today_usd": report.ai_cost_today,
            "last_bet_at": report.last_bet_time,
        }, indent=2))
    else:
        print(format_status_text(report))


def cmd_bets(args) -> None:
    """Show bet history."""
    from src.agent.main import bootstrap
    from src.storage.db import get_bets

    bootstrap(args.config)
    bets = get_bets(limit=args.limit, status_filter=args.status)

    if args.json:
        print(json.dumps(bets, indent=2, default=str))
        return

    if not bets:
        print("No bets found.")
        return

    header = f"{'Time':<17} {'Market':<38} {'Side':<4} {'Amount':>8} {'Status':<10} {'P&L':>8}"
    print(header)
    print("─" * 95)
    for b in bets:
        q = (b.get("question") or b.get("condition_id") or "")[:36]
        pnl = f"${b['pnl_usd']:+.2f}" if b.get("pnl_usd") is not None else "—"
        print(f"{str(b.get('created_at',''))[:16]:<17} {q:<38} {b.get('side',''):<4} ${b.get('amount_usd',0):>7.2f} {b.get('status',''):<10} {pnl:>8}")


def cmd_config(args) -> None:
    """Show or update config values."""
    import yaml

    config_path = Path(args.config)

    if args.action == "show":
        if not config_path.exists():
            print(f"Config file not found: {config_path}")
            sys.exit(1)
        with open(config_path) as f:
            print(f.read())

    elif args.action == "set":
        if not args.key or args.value is None:
            print("Usage: agent config set <key> <value>")
            sys.exit(1)

        data = {}
        if config_path.exists():
            with open(config_path) as f:
                data = yaml.safe_load(f) or {}

        # Support dot notation: risk.daily_loss_limit_usd
        keys = args.key.split(".")
        node = data
        for k in keys[:-1]:
            node = node.setdefault(k, {})

        old_val = node.get(keys[-1])
        try:
            new_val = float(args.value) if "." in args.value else int(args.value)
        except ValueError:
            new_val = args.value

        node[keys[-1]] = new_val
        with open(config_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False)

        print(f"Updated: {args.key} = {new_val} (was {old_val})")
        print("Note: Changes take effect on next scan cycle.")


def cmd_analyze(args) -> None:
    """Analyze a specific market with DeepSeek and show the estimate."""
    from src.agent.main import bootstrap, get_config
    from src.agent.scanner import fetch_crypto_markets
    from src.agent.estimator import estimate_probability
    from src.agent.signals import fetch_onchain_data
    from src.storage.db import get_market

    cfg = bootstrap(args.config)

    async def _run():
        market = get_market(args.market_id)
        if not market:
            # Try fetching fresh
            markets = await fetch_crypto_markets(max_results=500)
            market = next((m for m in markets if m.condition_id == args.market_id), None)
        if not market:
            print(f"Market not found: {args.market_id}")
            sys.exit(1)

        onchain = None
        if not args.no_onchain:
            onchain = await fetch_onchain_data(
                market.question,
                defillama_base=cfg.onchain.defillama_base_url,
                github_token=cfg.onchain.github_token,
                etherscan_key=cfg.onchain.etherscan_api_key,
            )

        signal = await estimate_probability(
            market=market,
            api_key=cfg.deepseek.api_key,
            model=cfg.deepseek.model,
            onchain=onchain,
        )

        if not signal:
            print("AI analysis failed.")
            return

        print(f"\nMarket:     {market.question}")
        print(f"Current:    YES {market.yes_price:.3f} | NO {market.no_price:.3f}")
        print(f"AI estimate:{signal.estimated_prob:.3f} ({signal.confidence} confidence)")
        print(f"Deviation:  {signal.deviation:+.3f}")
        print(f"Tokens:     {signal.ai_tokens_used} | Cost: ${signal.ai_cost_usd:.5f}")
        if onchain and args.verbose:
            print(f"\nOnchain data ({market.question[:40]}):")
            print(f"  Project:       {onchain.project_name}")
            print(f"  TVL:           {'${:,.0f}'.format(onchain.tvl_usd) if onchain.tvl_usd else 'N/A'}")
            print(f"  TVL 7d:        {'{:+.1f}%'.format(onchain.tvl_7d_change_pct) if onchain.tvl_7d_change_pct else 'N/A'}")
            print(f"  GitHub 30d:    {onchain.github_commits_30d or 'N/A'}")
            print(f"  Large xfers:   {onchain.large_transfers_24h or 'N/A'}")
            print(f"  Onchain used:  {signal.onchain_used}")
            if onchain.fetch_errors:
                print(f"  Errors:        {', '.join(onchain.fetch_errors)}")

    asyncio.run(_run())


def cmd_scan(args) -> None:
    """One-shot market scan without starting the scheduler."""
    from src.agent.main import bootstrap, get_config, to_risk_config
    from src.agent.scanner import fetch_crypto_markets, filter_tradeable

    cfg = bootstrap(args.config)
    risk = to_risk_config(cfg)

    async def _run():
        markets = await fetch_crypto_markets(categories=cfg.scanning.categories, max_results=300)
        tradeable = filter_tradeable(markets, top_n=risk.max_markets_per_ai_scan)
        print(f"Fetched {len(markets)} active crypto markets")
        print(f"After liquidity filter: {len(tradeable)} markets")
        for m in tradeable[:5]:
            print(f"  {m.condition_id[:20]}  YES:{m.yes_price:.3f}  Liquidity:${m.liquidity_usd:,.0f}  {m.question[:50]}")
        if len(tradeable) > 5:
            print(f"  ... and {len(tradeable)-5} more")

    asyncio.run(_run())


def cmd_force_bet(args) -> None:
    """Force a bet for testing (sandbox only)."""
    from src.agent.main import bootstrap, get_config, to_risk_config
    from src.storage.db import get_market, get_portfolio, insert_bet
    from src.models.bet import Bet
    from src.agent import portfolio as port_mgr

    cfg = bootstrap(args.config)
    if cfg.polymarket.chain_id == 137:
        print("ERROR: force-bet disabled on mainnet (chain_id=137). Use sandbox (80002).")
        sys.exit(1)

    portfolio = get_portfolio()
    market = get_market(args.market_id)
    if not market:
        print(f"Market not found: {args.market_id}")
        sys.exit(1)

    bet = Bet(
        id=None, condition_id=args.market_id,
        signal_id=0, side=args.side.upper(),
        amount_usd=args.amount,
        price_at_order=market.yes_price if args.side.upper() == "YES" else market.no_price,
        kelly_fraction=0.0, order_id="force-bet-test", status="filled",
    )
    bet_id = insert_bet(bet)
    port_mgr.deduct_bet(portfolio, args.amount)
    print(f"Force bet placed: {args.side.upper()} ${args.amount:.2f} on {args.market_id[:20]} (bet ID: {bet_id})")


def cmd_web(args) -> None:
    """Start the web dashboard."""
    from src.agent.main import bootstrap
    bootstrap(args.config)

    try:
        import uvicorn
    except ImportError:
        print("Missing dependency: pip install fastapi uvicorn jinja2")
        sys.exit(1)

    print(f"Dashboard starting at http://0.0.0.0:{args.port}")
    print(f"Access via: http://<your-vps-ip>:{args.port}")
    uvicorn.run("src.web.app:app", host=args.host, port=args.port, reload=False)


def cmd_simulate_loss(args) -> None:
    """Simulate a loss to test risk limits."""
    from src.agent.main import bootstrap
    from src.storage.db import get_portfolio, update_portfolio

    bootstrap(args.config)
    portfolio = get_portfolio()
    portfolio.daily_loss_usd = round(portfolio.daily_loss_usd + args.amount, 4)
    update_portfolio(portfolio)
    print(f"Simulated loss: +${args.amount:.2f}. Daily loss now: ${portfolio.daily_loss_usd:.2f}")


def main():
    parser = argparse.ArgumentParser(prog="agent", description="Polymarket AI Trading Agent")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    sub = parser.add_subparsers(dest="command")

    # check
    sub.add_parser("check", help="Verify connectivity to all services")

    # start
    p_start = sub.add_parser("start", help="Start the agent")
    p_start.add_argument("--dry-run", action="store_true", help="Analyze but don't place real bets")

    # stop
    sub.add_parser("stop", help="Send stop signal to running agent")

    # status
    p_status = sub.add_parser("status", help="Show agent status and portfolio")
    p_status.add_argument("--json", action="store_true")

    # bets
    p_bets = sub.add_parser("bets", help="Show bet history")
    p_bets.add_argument("--limit", type=int, default=20)
    p_bets.add_argument("--status", default="all", choices=["open", "closed", "all"])
    p_bets.add_argument("--json", action="store_true")

    # config
    p_config = sub.add_parser("config", help="Show or update config")
    p_config.add_argument("action", choices=["show", "set"])
    p_config.add_argument("key", nargs="?")
    p_config.add_argument("value", nargs="?")

    # analyze
    p_analyze = sub.add_parser("analyze", help="Analyze a specific market")
    p_analyze.add_argument("--market-id", required=True)
    p_analyze.add_argument("--verbose", action="store_true")
    p_analyze.add_argument("--no-onchain", action="store_true")

    # scan
    p_scan = sub.add_parser("scan", help="One-shot market scan")
    p_scan.add_argument("--once", action="store_true")
    p_scan.add_argument("--dry-run", action="store_true")

    # force-bet (sandbox testing)
    p_fb = sub.add_parser("force-bet", help="Force a bet (sandbox only)")
    p_fb.add_argument("--market-id", required=True)
    p_fb.add_argument("--side", required=True, choices=["YES", "NO", "yes", "no"])
    p_fb.add_argument("--amount", type=float, required=True)

    # simulate-loss
    p_sl = sub.add_parser("simulate-loss", help="Simulate a loss to test risk limits")
    p_sl.add_argument("--amount", type=float, required=True)

    # web dashboard
    p_web = sub.add_parser("web", help="Start web dashboard")
    p_web.add_argument("--port", type=int, default=8080)
    p_web.add_argument("--host", default="0.0.0.0")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    dispatch = {
        "check": cmd_check,
        "start": cmd_start,
        "stop": cmd_stop,
        "status": cmd_status,
        "bets": cmd_bets,
        "config": cmd_config,
        "analyze": cmd_analyze,
        "scan": cmd_scan,
        "force-bet": cmd_force_bet,
        "simulate-loss": cmd_simulate_loss,
        "web": cmd_web,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
