from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List


@dataclass
class OnchainSnapshot:
    id: Optional[int]
    signal_id: Optional[int]
    project_name: str
    tvl_usd: Optional[float]
    tvl_7d_change_pct: Optional[float]
    github_commits_30d: Optional[int]
    large_transfers_24h: Optional[int]
    data_sources: List[str] = field(default_factory=list)
    fetch_errors: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def available(self) -> bool:
        return any([
            self.tvl_usd is not None,
            self.github_commits_30d is not None,
            self.large_transfers_24h is not None,
        ])


@dataclass
class Signal:
    id: Optional[int]
    condition_id: str
    estimated_prob: float
    market_price: float
    deviation: float
    confidence: str          # "high" | "medium" | "low"
    onchain_used: bool
    ai_tokens_used: int
    ai_cost_usd: float
    created_at: datetime = field(default_factory=datetime.utcnow)
    onchain_snapshot: Optional[OnchainSnapshot] = None

    @property
    def is_actionable(self, threshold: float = 0.08) -> bool:
        return abs(self.deviation) > threshold

    @property
    def recommended_side(self) -> str:
        return "YES" if self.deviation > 0 else "NO"


@dataclass
class OperatingCost:
    id: Optional[int]
    cost_type: str           # "ai_inference" | "tx_fee"
    amount_usd: float
    description: str
    created_at: datetime = field(default_factory=datetime.utcnow)
