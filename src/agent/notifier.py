import logging

import httpx

logger = logging.getLogger(__name__)

_bot_token: str = ""
_chat_id: str = ""


def setup_notifier(bot_token: str, chat_id: str) -> None:
    global _bot_token, _chat_id
    _bot_token = bot_token
    _chat_id = str(chat_id)


async def _send(text: str) -> None:
    if not _bot_token or not _chat_id:
        return
    url = f"https://api.telegram.org/bot{_bot_token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json={
                "chat_id": _chat_id,
                "text": text,
                "parse_mode": "Markdown",
            })
            if resp.status_code != 200:
                logger.warning("Telegram notify failed: %s %s", resp.status_code, resp.text[:200])
    except Exception as e:
        logger.warning("Telegram notify error: %s", e)


async def notify_bet_placed(side: str, amount: float, question: str, price: float) -> None:
    q = question[:60] + ("…" if len(question) > 60 else "")
    await _send(
        f"🎯 *Agent 下注*\n"
        f"方向: `{side}`\n"
        f"金额: `${amount:.2f}`\n"
        f"价格: `{price:.3f}`\n"
        f"市场: {q}"
    )


async def notify_bet_settled(side: str, amount: float, pnl: float, question: str) -> None:
    q = question[:60] + ("…" if len(question) > 60 else "")
    icon = "✅" if pnl >= 0 else "❌"
    sign = "+" if pnl >= 0 else ""
    await _send(
        f"{icon} *结算 — {'盈利' if pnl >= 0 else '亏损'}*\n"
        f"方向: `{side}`\n"
        f"本金: `${amount:.2f}`\n"
        f"P&L: `{sign}${pnl:.2f}`\n"
        f"市场: {q}"
    )


async def notify_daily_loss_limit(daily_loss: float, limit: float) -> None:
    await _send(
        f"⚠️ *Agent 已暂停 — 日亏损触顶*\n"
        f"今日亏损: `${daily_loss:.2f}`\n"
        f"上限: `${limit:.2f}`\n"
        f"明日 00:00 UTC 自动恢复"
    )


async def notify_agent_error(error: str) -> None:
    await _send(
        f"🔴 *Agent 错误*\n"
        f"`{error[:300]}`"
    )


async def notify_cycle_summary(markets: int, signals: int, bets: int, ai_cost: float) -> None:
    await _send(
        f"📊 *扫描完成*\n"
        f"扫描市场: `{markets}` 个\n"
        f"发现信号: `{signals}` 个\n"
        f"下注: `{bets}` 笔\n"
        f"AI 费用: `${ai_cost:.4f}`"
    )
