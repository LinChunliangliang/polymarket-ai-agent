from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Portfolio:
    id: int = 1
    starting_balance_usd: float = 500.0
    current_balance_usd: float = 500.0
    total_wagered_usd: float = 0.0
    total_ai_cost_usd: float = 0.0
    total_pnl_usd: float = 0.0
    daily_loss_usd: float = 0.0
    last_updated_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def net_return_pct(self) -> float:
        if self.starting_balance_usd == 0:
            return 0.0
        return (self.total_pnl_usd / self.starting_balance_usd) * 100


@dataclass
class RiskConfig:
    max_position_pct: float = 0.06
    daily_loss_limit_usd: float = 75.0
    min_bet_usd: float = 5.0
    deviation_threshold: float = 0.08
    min_liquidity_multiple: float = 3.0
    kelly_fraction: float = 0.25
    ai_scan_interval_min: int = 60
    price_check_interval_min: int = 10
    max_markets_per_ai_scan: int = 50
    starting_balance_usd: float = 500.0
