import json
import logging
from datetime import datetime
from typing import Optional

from openai import AsyncOpenAI

from src.models.market import Market
from src.models.signal import Signal, OnchainSnapshot, OperatingCost
from src.models.portfolio import RiskConfig
from src.storage import db

logger = logging.getLogger(__name__)

# DeepSeek pricing (V4-Flash): input $0.14/M, output $0.28/M tokens
PRICE_INPUT_PER_M = 0.14
PRICE_OUTPUT_PER_M = 0.28

SYSTEM_PROMPT = """You are a prediction market analyst specializing in cryptocurrency markets.
Your task is to estimate the true probability of a binary prediction market resolving YES.

Guidelines:
- Base your estimate on the market question, current context, and any on-chain data provided
- Be calibrated: if uncertain, reflect that via confidence level
- Do NOT anchor to the current market price
- Return ONLY valid JSON with no explanation text outside the JSON structure"""


def _build_client(api_key: str, model: str) -> tuple:
    client = AsyncOpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com/v1",
    )
    return client, model


async def estimate_probability(
    market: Market,
    api_key: str,
    model: str = "deepseek-chat",
    onchain: Optional[OnchainSnapshot] = None,
    dry_run: bool = False,
) -> Optional[Signal]:
    """Call DeepSeek to estimate true probability for a market. Returns Signal or None on failure."""

    user_payload = {
        "market": {
            "question": market.question,
            "end_date": market.end_datetime.date().isoformat(),
            "current_yes_price": round(market.yes_price, 4),
            "volume_24h_usd": round(market.volume_usd, 2),
        },
        "context_date": datetime.utcnow().date().isoformat(),
    }

    if onchain and onchain.available:
        user_payload["onchain_signals"] = {
            "available": True,
            "tvl_change_7d_pct": onchain.tvl_7d_change_pct,
            "github_commits_30d": onchain.github_commits_30d,
            "large_transfers_24h": onchain.large_transfers_24h,
            "notes": _onchain_notes(onchain),
        }
    else:
        user_payload["onchain_signals"] = {"available": False}

    if dry_run:
        # Return a neutral mock signal without calling API
        return Signal(
            id=None, condition_id=market.condition_id,
            estimated_prob=market.yes_price,
            market_price=market.yes_price,
            deviation=0.0, confidence="low",
            onchain_used=False, ai_tokens_used=0, ai_cost_usd=0.0,
        )

    client, mdl = _build_client(api_key, model)
    try:
        resp = await client.chat.completions.create(
            model=mdl,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            temperature=0.2,
            max_tokens=400,
        )
    except Exception as e:
        logger.error("DeepSeek API error for %s: %s", market.condition_id, e)
        return None

    raw = resp.choices[0].message.content.strip()
    usage = resp.usage

    # Parse JSON response
    parsed = _parse_response(raw)
    if parsed is None:
        # Retry once with explicit JSON reminder
        try:
            resp2 = await client.chat.completions.create(
                model=mdl,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": "Return ONLY valid JSON as described. No other text."},
                ],
                temperature=0.1,
                max_tokens=400,
            )
            raw = resp2.choices[0].message.content.strip()
            usage = resp2.usage
            parsed = _parse_response(raw)
        except Exception:
            pass

    if parsed is None:
        logger.warning("Could not parse AI response for %s", market.condition_id)
        return None

    # Clamp probability
    prob = max(0.01, min(0.99, float(parsed["estimated_probability"])))
    confidence = parsed.get("confidence", "medium")
    if confidence not in ("high", "medium", "low"):
        confidence = "medium"

    # Calculate cost
    input_tokens = usage.prompt_tokens if usage else 600
    output_tokens = usage.completion_tokens if usage else 100
    cost = (input_tokens * PRICE_INPUT_PER_M + output_tokens * PRICE_OUTPUT_PER_M) / 1_000_000

    deviation = round(prob - market.yes_price, 4)

    signal = Signal(
        id=None,
        condition_id=market.condition_id,
        estimated_prob=prob,
        market_price=market.yes_price,
        deviation=deviation,
        confidence=confidence,
        onchain_used=bool(onchain and onchain.available),
        ai_tokens_used=input_tokens + output_tokens,
        ai_cost_usd=cost,
    )

    # Persist signal
    signal_id = db.insert_signal(signal)
    signal.id = signal_id

    # Record operating cost
    cost_record = OperatingCost(
        id=None,
        cost_type="ai_inference",
        amount_usd=cost,
        description=f"DeepSeek {mdl}: {market.condition_id[:20]}",
    )
    db.insert_cost(cost_record)

    logger.debug(
        "Signal %s: est=%.3f mkt=%.3f dev=%+.3f conf=%s cost=$%.5f",
        market.condition_id[:16], prob, market.yes_price, deviation, confidence, cost,
    )
    return signal


def _parse_response(raw: str) -> Optional[dict]:
    # Strip markdown code fences if present
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        data = json.loads(text)
        if "estimated_probability" in data:
            return data
    except Exception:
        pass
    return None


def _onchain_notes(snap: OnchainSnapshot) -> str:
    parts = []
    if snap.tvl_7d_change_pct is not None:
        parts.append(f"TVL 7d change: {snap.tvl_7d_change_pct:+.1f}%")
    if snap.github_commits_30d is not None:
        parts.append(f"GitHub commits 30d: {snap.github_commits_30d}")
    if snap.large_transfers_24h is not None:
        parts.append(f"Large transfers 24h: {snap.large_transfers_24h}")
    return "; ".join(parts) if parts else "no data"
