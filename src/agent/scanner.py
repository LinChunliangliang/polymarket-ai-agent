import logging
from datetime import datetime, timedelta
from typing import List

import httpx

from src.models.market import Market
from src.storage import db

logger = logging.getLogger(__name__)

CLOB_BASE = "https://clob.polymarket.com"
GAMMA_BASE = "https://gamma-api.polymarket.com"


async def fetch_crypto_markets(
    categories: List[str] = None,
    max_results: int = 200,
) -> List[Market]:
    """Fetch active crypto markets from Polymarket Gamma API."""
    if categories is None:
        categories = ["crypto"]

    markets: List[Market] = []
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.get(
                f"{GAMMA_BASE}/markets",
                params={
                    "active": "true",
                    "closed": "false",
                    "limit": max_results,
                    "tag_slug": "crypto",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            items = data if isinstance(data, list) else data.get("data", data.get("markets", []))
        except Exception as e:
            logger.error("Failed to fetch markets from Gamma API: %s", e)
            return []

    for item in items:
        try:
            market = _parse_market(item)
            if market:
                markets.append(market)
                db.upsert_market(market)
        except Exception as e:
            logger.debug("Skipping market parse error: %s", e)

    logger.info("Fetched %d active crypto markets", len(markets))
    return markets


def filter_tradeable(
    markets: List[Market],
    min_liquidity_usd: float = 100.0,
    min_hours_to_end: int = 24,
    top_n: int = 50,
) -> List[Market]:
    """Filter and rank markets by liquidity, excluding near-expiry and illiquid ones."""
    now = datetime.utcnow()
    cutoff = now + timedelta(hours=min_hours_to_end)
    filtered = [
        m for m in markets
        if m.is_active
        and 0.01 < m.yes_price < 0.99
        and m.end_datetime > cutoff
        and m.liquidity_usd >= min_liquidity_usd
    ]
    filtered.sort(key=lambda m: m.liquidity_usd, reverse=True)
    return filtered[:top_n]


async def fetch_prices(condition_ids: List[str]) -> dict:
    """Quick price refresh for a list of markets. Returns {condition_id: yes_price}."""
    prices = {}
    async with httpx.AsyncClient(timeout=20) as client:
        for cid in condition_ids:
            try:
                resp = await client.get(f"{GAMMA_BASE}/markets/{cid}")
                if resp.status_code == 200:
                    data = resp.json()
                    price = _extract_yes_price(data)
                    if price is not None:
                        prices[cid] = price
            except Exception as e:
                logger.debug("Price fetch error for %s: %s", cid, e)
    return prices


def _parse_market(item: dict) -> Market | None:
    cid = item.get("conditionId") or item.get("condition_id") or item.get("id")
    if not cid:
        return None

    question = item.get("question") or item.get("title") or ""
    yes_price = _extract_yes_price(item)
    if yes_price is None:
        return None

    end_str = item.get("endDate") or item.get("end_date_iso") or item.get("endDateIso")
    if not end_str:
        return None
    try:
        end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None

    # Extract YES/NO token IDs for CLOB order placement
    yes_token_id = ""
    no_token_id = ""
    clob_token_ids = item.get("clobTokenIds") or item.get("clob_token_ids")
    if clob_token_ids:
        if isinstance(clob_token_ids, str):
            import json
            try:
                clob_token_ids = json.loads(clob_token_ids)
            except Exception:
                clob_token_ids = []
        if isinstance(clob_token_ids, list) and len(clob_token_ids) >= 2:
            yes_token_id = str(clob_token_ids[0])
            no_token_id = str(clob_token_ids[1])

    return Market(
        condition_id=str(cid),
        question=question,
        category="crypto",
        yes_price=yes_price,
        no_price=round(1.0 - yes_price, 4),
        volume_usd=float(item.get("volume", item.get("volumeNum", 0)) or 0),
        liquidity_usd=float(item.get("liquidity", item.get("liquidityNum", 0)) or 0),
        end_datetime=end_dt,
        yes_token_id=yes_token_id,
        no_token_id=no_token_id,
        last_fetched_at=datetime.utcnow(),
        is_active=True,
    )


def _extract_yes_price(item: dict) -> float | None:
    # Try several common field names
    for key in ("outcomePrices", "outcome_prices"):
        prices = item.get(key)
        if prices:
            if isinstance(prices, list) and len(prices) >= 1:
                return float(prices[0])
            if isinstance(prices, str):
                import json
                try:
                    arr = json.loads(prices)
                    if arr:
                        return float(arr[0])
                except Exception:
                    pass
    for key in ("bestAsk", "best_ask", "lastTradePrice", "last_trade_price"):
        v = item.get(key)
        if v is not None:
            try:
                return float(v)
            except Exception:
                pass
    return None
