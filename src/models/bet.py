from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Bet:
    id: Optional[int]
    condition_id: str
    signal_id: int
    side: str                # "YES" | "NO"
    amount_usd: float
    price_at_order: float
    kelly_fraction: float
    order_id: Optional[str]
    status: str = "pending"  # pending | filled | cancelled | won | lost
    pnl_usd: Optional[float] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    settled_at: Optional[datetime] = None

    @property
    def is_open(self) -> bool:
        return self.status in ("pending", "filled")

    @property
    def potential_payout(self) -> float:
        if self.price_at_order <= 0:
            return 0.0
        return self.amount_usd / self.price_at_order
