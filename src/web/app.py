from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.storage.db import init_db, get_bets
from src.agent.reporter import get_status

def _get_arb():
    try:
        from src.agent.scheduler import get_last_arb
        return get_last_arb()
    except Exception:
        return {"opportunities": [], "scanned_at": None}

app = FastAPI(title="Polymarket Agent Dashboard")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@app.on_event("startup")
def startup():
    init_db()


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    report = get_status()
    bets = get_bets(limit=50, status_filter="all")
    arb = _get_arb()
    return templates.TemplateResponse(request, "index.html", {
        "report": report,
        "bets": bets,
        "arb": arb,
    })


@app.get("/api/status")
async def api_status():
    report = get_status()
    return {
        "status": report.status,
        "pid": report.pid,
        "portfolio": {
            "starting_usd": report.portfolio_starting,
            "current_usd": report.portfolio_current,
            "pnl_usd": report.portfolio_pnl,
            "pnl_pct": round(report.portfolio_pnl_pct, 2),
        },
        "open_bets": report.open_bets,
        "open_bets_at_risk_usd": report.open_bets_at_risk,
        "daily_loss_usd": report.daily_loss,
        "daily_loss_limit_usd": report.daily_loss_limit,
        "ai_cost_today_usd": report.ai_cost_today,
        "ai_cost_total_usd": report.total_ai_cost,
        "last_bet_at": report.last_bet_time,
    }


@app.get("/api/bets")
async def api_bets(limit: int = 50, status: str = "all"):
    return get_bets(limit=limit, status_filter=status)


@app.get("/api/arb")
async def api_arb():
    data = _get_arb()
    opps = data["opportunities"]
    return {
        "scanned_at": data["scanned_at"],
        "count": len(opps),
        "opportunities": [
            {
                "condition_id": o.market.condition_id,
                "question": o.market.question,
                "yes_price": o.yes_price,
                "no_price": o.no_price,
                "sum_price": o.sum_price,
                "net_profit_pct": round(o.net_profit_pct * 100, 3),
                "liquidity_usd": o.market.liquidity_usd,
            }
            for o in opps[:20]
        ],
    }
