from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Market:
    condition_id: str
    question: str
    category: str
    yes_price: float
    no_price: float
    volume_usd: float
    liquidity_usd: float
    end_datetime: datetime
    yes_token_id: str = ""    # Polymarket CLOB token ID for YES outcome
    no_token_id: str = ""     # Polymarket CLOB token ID for NO outcome
    last_fetched_at: datetime = field(default_factory=datetime.utcnow)
    is_active: bool = True

    def is_tradeable(self) -> bool:
        return (
            self.is_active
            and 0.01 < self.yes_price < 0.99
            and self.end_datetime > datetime.utcnow()
        )

    def has_sufficient_liquidity(self, bet_amount: float, multiplier: float = 3.0) -> bool:
        return self.liquidity_usd >= bet_amount * multiplier
