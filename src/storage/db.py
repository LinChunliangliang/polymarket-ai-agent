import sqlite3
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from src.models.market import Market
from src.models.signal import Signal, OnchainSnapshot, OperatingCost
from src.models.bet import Bet
from src.models.portfolio import Portfolio

logger = logging.getLogger(__name__)

DB_PATH = Path("agent.db")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS markets (
            condition_id TEXT PRIMARY KEY,
            question TEXT NOT NULL,
            category TEXT NOT NULL,
            yes_price REAL NOT NULL,
            no_price REAL NOT NULL,
            volume_usd REAL DEFAULT 0,
            liquidity_usd REAL DEFAULT 0,
            end_datetime TEXT NOT NULL,
            last_fetched_at TEXT NOT NULL,
            is_active INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            condition_id TEXT NOT NULL,
            estimated_prob REAL NOT NULL,
            market_price REAL NOT NULL,
            deviation REAL NOT NULL,
            confidence TEXT NOT NULL,
            onchain_used INTEGER DEFAULT 0,
            ai_tokens_used INTEGER DEFAULT 0,
            ai_cost_usd REAL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (condition_id) REFERENCES markets(condition_id)
        );

        CREATE TABLE IF NOT EXISTS onchain_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id INTEGER NOT NULL,
            project_name TEXT NOT NULL,
            tvl_usd REAL,
            tvl_7d_change_pct REAL,
            github_commits_30d INTEGER,
            large_transfers_24h INTEGER,
            data_sources TEXT DEFAULT '[]',
            fetch_errors TEXT DEFAULT '[]',
            created_at TEXT NOT NULL,
            FOREIGN KEY (signal_id) REFERENCES signals(id)
        );

        CREATE TABLE IF NOT EXISTS bets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            condition_id TEXT NOT NULL,
            signal_id INTEGER NOT NULL,
            side TEXT NOT NULL,
            amount_usd REAL NOT NULL,
            price_at_order REAL NOT NULL,
            kelly_fraction REAL NOT NULL,
            order_id TEXT,
            status TEXT DEFAULT 'pending',
            pnl_usd REAL,
            created_at TEXT NOT NULL,
            settled_at TEXT,
            FOREIGN KEY (condition_id) REFERENCES markets(condition_id),
            FOREIGN KEY (signal_id) REFERENCES signals(id)
        );

        CREATE TABLE IF NOT EXISTS portfolio (
            id INTEGER PRIMARY KEY DEFAULT 1,
            starting_balance_usd REAL NOT NULL,
            current_balance_usd REAL NOT NULL,
            total_wagered_usd REAL DEFAULT 0,
            total_ai_cost_usd REAL DEFAULT 0,
            total_pnl_usd REAL DEFAULT 0,
            daily_loss_usd REAL DEFAULT 0,
            last_updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS operating_costs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cost_type TEXT NOT NULL,
            amount_usd REAL NOT NULL,
            description TEXT,
            created_at TEXT NOT NULL
        );
        """)
    logger.info("Database initialized at %s", DB_PATH)


def _now() -> str:
    return datetime.utcnow().isoformat()


# ── Markets ──────────────────────────────────────────────────────────────────

def upsert_market(m: Market) -> None:
    with get_conn() as conn:
        conn.execute("""
        INSERT INTO markets (condition_id, question, category, yes_price, no_price,
            volume_usd, liquidity_usd, end_datetime, last_fetched_at, is_active)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(condition_id) DO UPDATE SET
            yes_price=excluded.yes_price, no_price=excluded.no_price,
            volume_usd=excluded.volume_usd, liquidity_usd=excluded.liquidity_usd,
            last_fetched_at=excluded.last_fetched_at, is_active=excluded.is_active
        """, (m.condition_id, m.question, m.category, m.yes_price, m.no_price,
              m.volume_usd, m.liquidity_usd, m.end_datetime.isoformat(),
              m.last_fetched_at.isoformat(), int(m.is_active)))


def get_market(condition_id: str) -> Optional[Market]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM markets WHERE condition_id=?", (condition_id,)).fetchone()
    return _row_to_market(row) if row else None


def _row_to_market(row) -> Market:
    return Market(
        condition_id=row["condition_id"],
        question=row["question"],
        category=row["category"],
        yes_price=row["yes_price"],
        no_price=row["no_price"],
        volume_usd=row["volume_usd"],
        liquidity_usd=row["liquidity_usd"],
        end_datetime=datetime.fromisoformat(row["end_datetime"]),
        last_fetched_at=datetime.fromisoformat(row["last_fetched_at"]),
        is_active=bool(row["is_active"]),
    )


# ── Signals ───────────────────────────────────────────────────────────────────

def insert_signal(s: Signal) -> int:
    with get_conn() as conn:
        cur = conn.execute("""
        INSERT INTO signals (condition_id, estimated_prob, market_price, deviation,
            confidence, onchain_used, ai_tokens_used, ai_cost_usd, created_at)
        VALUES (?,?,?,?,?,?,?,?,?)
        """, (s.condition_id, s.estimated_prob, s.market_price, s.deviation,
              s.confidence, int(s.onchain_used), s.ai_tokens_used, s.ai_cost_usd,
              s.created_at.isoformat()))
        return cur.lastrowid


def insert_onchain_snapshot(snap: OnchainSnapshot) -> int:
    with get_conn() as conn:
        cur = conn.execute("""
        INSERT INTO onchain_snapshots (signal_id, project_name, tvl_usd, tvl_7d_change_pct,
            github_commits_30d, large_transfers_24h, data_sources, fetch_errors, created_at)
        VALUES (?,?,?,?,?,?,?,?,?)
        """, (snap.signal_id, snap.project_name, snap.tvl_usd, snap.tvl_7d_change_pct,
              snap.github_commits_30d, snap.large_transfers_24h,
              json.dumps(snap.data_sources), json.dumps(snap.fetch_errors),
              snap.created_at.isoformat()))
        return cur.lastrowid


# ── Bets ──────────────────────────────────────────────────────────────────────

def insert_bet(b: Bet) -> int:
    with get_conn() as conn:
        cur = conn.execute("""
        INSERT INTO bets (condition_id, signal_id, side, amount_usd, price_at_order,
            kelly_fraction, order_id, status, created_at)
        VALUES (?,?,?,?,?,?,?,?,?)
        """, (b.condition_id, b.signal_id, b.side, b.amount_usd, b.price_at_order,
              b.kelly_fraction, b.order_id, b.status, b.created_at.isoformat()))
        return cur.lastrowid


def update_bet_status(bet_id: int, status: str, pnl_usd: Optional[float] = None,
                      order_id: Optional[str] = None) -> None:
    with get_conn() as conn:
        if status in ("won", "lost"):
            conn.execute("""
            UPDATE bets SET status=?, pnl_usd=?, settled_at=? WHERE id=?
            """, (status, pnl_usd, _now(), bet_id))
        else:
            if order_id:
                conn.execute("UPDATE bets SET status=?, order_id=? WHERE id=?",
                             (status, order_id, bet_id))
            else:
                conn.execute("UPDATE bets SET status=? WHERE id=?", (status, bet_id))


def get_open_bets() -> List[Bet]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM bets WHERE status IN ('pending','filled')"
        ).fetchall()
    return [_row_to_bet(r) for r in rows]


def get_bets(limit: int = 20, status_filter: Optional[str] = None) -> List[dict]:
    with get_conn() as conn:
        if status_filter and status_filter != "all":
            rows = conn.execute("""
            SELECT b.*, m.question FROM bets b
            LEFT JOIN markets m ON b.condition_id = m.condition_id
            WHERE b.status=? ORDER BY b.created_at DESC LIMIT ?
            """, (status_filter, limit)).fetchall()
        else:
            rows = conn.execute("""
            SELECT b.*, m.question FROM bets b
            LEFT JOIN markets m ON b.condition_id = m.condition_id
            ORDER BY b.created_at DESC LIMIT ?
            """, (limit,)).fetchall()
    return [dict(r) for r in rows]


def _row_to_bet(row) -> Bet:
    return Bet(
        id=row["id"], condition_id=row["condition_id"], signal_id=row["signal_id"],
        side=row["side"], amount_usd=row["amount_usd"], price_at_order=row["price_at_order"],
        kelly_fraction=row["kelly_fraction"], order_id=row["order_id"],
        status=row["status"], pnl_usd=row["pnl_usd"],
        created_at=datetime.fromisoformat(row["created_at"]),
        settled_at=datetime.fromisoformat(row["settled_at"]) if row["settled_at"] else None,
    )


# ── Portfolio ─────────────────────────────────────────────────────────────────

def get_portfolio() -> Portfolio:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM portfolio WHERE id=1").fetchone()
    if row:
        return Portfolio(
            id=row["id"],
            starting_balance_usd=row["starting_balance_usd"],
            current_balance_usd=row["current_balance_usd"],
            total_wagered_usd=row["total_wagered_usd"],
            total_ai_cost_usd=row["total_ai_cost_usd"],
            total_pnl_usd=row["total_pnl_usd"],
            daily_loss_usd=row["daily_loss_usd"],
            last_updated_at=datetime.fromisoformat(row["last_updated_at"]),
        )
    return Portfolio()


def update_portfolio(p: Portfolio) -> None:
    with get_conn() as conn:
        conn.execute("""
        INSERT INTO portfolio (id, starting_balance_usd, current_balance_usd,
            total_wagered_usd, total_ai_cost_usd, total_pnl_usd, daily_loss_usd, last_updated_at)
        VALUES (1,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
            current_balance_usd=excluded.current_balance_usd,
            total_wagered_usd=excluded.total_wagered_usd,
            total_ai_cost_usd=excluded.total_ai_cost_usd,
            total_pnl_usd=excluded.total_pnl_usd,
            daily_loss_usd=excluded.daily_loss_usd,
            last_updated_at=excluded.last_updated_at
        """, (p.starting_balance_usd, p.current_balance_usd, p.total_wagered_usd,
              p.total_ai_cost_usd, p.total_pnl_usd, p.daily_loss_usd,
              p.last_updated_at.isoformat()))


# ── Operating Costs ───────────────────────────────────────────────────────────

def insert_cost(cost: OperatingCost) -> None:
    with get_conn() as conn:
        conn.execute("""
        INSERT INTO operating_costs (cost_type, amount_usd, description, created_at)
        VALUES (?,?,?,?)
        """, (cost.cost_type, cost.amount_usd, cost.description, cost.created_at.isoformat()))


def get_total_ai_cost_today() -> float:
    today = datetime.utcnow().date().isoformat()
    with get_conn() as conn:
        row = conn.execute("""
        SELECT COALESCE(SUM(amount_usd),0) as total FROM operating_costs
        WHERE cost_type='ai_inference' AND created_at LIKE ?
        """, (f"{today}%",)).fetchone()
    return row["total"]
