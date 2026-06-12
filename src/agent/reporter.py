import os
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from src.storage.db import get_portfolio, get_bets, get_total_ai_cost_today

logger = logging.getLogger(__name__)

PID_FILE = Path("agent.pid")


@dataclass
class StatusReport:
    status: str               # "running" | "paused" | "stopped"
    pid: Optional[int]
    uptime_seconds: Optional[float]
    portfolio_starting: float
    portfolio_current: float
    portfolio_pnl: float
    portfolio_pnl_pct: float
    open_bets: int
    open_bets_at_risk: float
    daily_loss: float
    daily_loss_limit: float
    total_ai_cost: float
    ai_cost_today: float
    last_bet_time: Optional[str]
    recent_bets: List[dict]


def get_status(daily_loss_limit: float = 75.0) -> StatusReport:
    portfolio = get_portfolio()
    recent_bets = get_bets(limit=5, status_filter="all")
    open_bets_list = get_bets(limit=100, status_filter="open")

    open_count = len(open_bets_list)
    at_risk = sum(b.get("amount_usd", 0) for b in open_bets_list)
    last_bet_time = recent_bets[0].get("created_at") if recent_bets else None

    pid = None
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
        except Exception:
            pass

    status = "stopped"
    if pid:
        try:
            os.kill(pid, 0)
            status = "running"
        except OSError:
            status = "stopped"
            pid = None

    if status == "running" and portfolio.daily_loss_usd >= daily_loss_limit:
        status = "paused"

    pnl_pct = (portfolio.total_pnl_usd / portfolio.starting_balance_usd * 100
               if portfolio.starting_balance_usd else 0)

    return StatusReport(
        status=status,
        pid=pid,
        uptime_seconds=None,
        portfolio_starting=portfolio.starting_balance_usd,
        portfolio_current=portfolio.current_balance_usd,
        portfolio_pnl=portfolio.total_pnl_usd,
        portfolio_pnl_pct=pnl_pct,
        open_bets=open_count,
        open_bets_at_risk=at_risk,
        daily_loss=portfolio.daily_loss_usd,
        daily_loss_limit=daily_loss_limit,
        total_ai_cost=portfolio.total_ai_cost_usd,
        ai_cost_today=get_total_ai_cost_today(),
        last_bet_time=last_bet_time,
        recent_bets=recent_bets,
    )


def format_status_text(report: StatusReport) -> str:
    pnl_sign = "+" if report.portfolio_pnl >= 0 else ""
    lines = [
        "── Agent Status " + "─" * 40,
        f"  Status:        {report.status.upper()}" + (f" (PID {report.pid})" if report.pid else ""),
        f"  Last bet:      {report.last_bet_time or 'never'}",
        "",
        "── Portfolio " + "─" * 43,
        f"  Starting:      ${report.portfolio_starting:.2f}",
        f"  Current:       ${report.portfolio_current:.2f}  ({pnl_sign}${report.portfolio_pnl:.2f} / {pnl_sign}{report.portfolio_pnl_pct:.1f}%)",
        f"  Open bets:     {report.open_bets}  (${report.open_bets_at_risk:.2f} at risk)",
        f"  AI costs:      ${report.total_ai_cost:.4f} total  |  ${report.ai_cost_today:.4f} today",
        f"  Daily loss:    ${report.daily_loss:.2f} / ${report.daily_loss_limit:.2f} limit",
    ]

    if report.recent_bets:
        lines += ["", "── Recent Bets " + "─" * 41]
        for b in report.recent_bets:
            q = (b.get("question") or b.get("condition_id") or "")[:38]
            pnl_str = f"  P&L ${b['pnl_usd']:+.2f}" if b.get("pnl_usd") is not None else ""
            lines.append(
                f"  {b.get('created_at','')[:16]}  {q:<38}  {b.get('side',''):<3}  ${b.get('amount_usd',0):.2f}  {b.get('status','').upper()}{pnl_str}"
            )

    return "\n".join(lines)
