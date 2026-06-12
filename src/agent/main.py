import logging
import logging.handlers
import os
import signal
import sys
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field

from src.models.portfolio import RiskConfig
from src.storage.db import init_db, get_portfolio, update_portfolio
from src.models.portfolio import Portfolio


# ── Config schema (Pydantic) ──────────────────────────────────────────────────

class PolymarketConfig(BaseModel):
    private_key: str = ""
    chain_id: int = 80002


class DeepseekConfig(BaseModel):
    api_key: str = ""
    model: str = "deepseek-chat"


class OnchainConfig(BaseModel):
    defillama_base_url: str = "https://api.defillama.com"
    github_token: str = ""
    etherscan_api_key: str = ""


class RiskConfigYaml(BaseModel):
    starting_balance_usd: float = 500.0
    max_position_pct: float = 0.06
    daily_loss_limit_usd: float = 75.0
    min_bet_usd: float = 5.0
    deviation_threshold: float = 0.08
    min_liquidity_multiple: float = 3.0
    kelly_fraction: float = 0.25


class ScanningConfig(BaseModel):
    ai_scan_interval_min: int = 60
    price_check_interval_min: int = 10
    max_markets_per_ai_scan: int = 50
    categories: list = Field(default_factory=lambda: ["crypto"])


class LoggingConfig(BaseModel):
    level: str = "INFO"
    file: str = "logs/agent.log"
    max_size_mb: int = 50
    backup_count: int = 7


class NotifyConfig(BaseModel):
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    notify_on_bet: bool = True
    notify_on_settle: bool = True
    notify_on_loss_limit: bool = True
    notify_cycle_summary: bool = False


class AppConfig(BaseModel):
    polymarket: PolymarketConfig = Field(default_factory=PolymarketConfig)
    deepseek: DeepseekConfig = Field(default_factory=DeepseekConfig)
    onchain: OnchainConfig = Field(default_factory=OnchainConfig)
    risk: RiskConfigYaml = Field(default_factory=RiskConfigYaml)
    scanning: ScanningConfig = Field(default_factory=ScanningConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    notify: NotifyConfig = Field(default_factory=NotifyConfig)


_config: Optional[AppConfig] = None


def load_config(path: str = "config.yaml") -> AppConfig:
    global _config
    data = {}
    if Path(path).exists():
        with open(path) as f:
            data = yaml.safe_load(f) or {}

    cfg = AppConfig(**data)

    # Environment variable overrides
    if pk := os.environ.get("POLY_PRIVATE_KEY"):
        cfg.polymarket.private_key = pk
    if ak := os.environ.get("DEEPSEEK_API_KEY"):
        cfg.deepseek.api_key = ak
    if gt := os.environ.get("GITHUB_TOKEN"):
        cfg.onchain.github_token = gt
    if ek := os.environ.get("ETHERSCAN_API_KEY"):
        cfg.onchain.etherscan_api_key = ek

    _config = cfg
    return cfg


def get_config() -> AppConfig:
    if _config is None:
        return load_config()
    return _config


def to_risk_config(cfg: AppConfig) -> RiskConfig:
    r = cfg.risk
    s = cfg.scanning
    return RiskConfig(
        max_position_pct=r.max_position_pct,
        daily_loss_limit_usd=r.daily_loss_limit_usd,
        min_bet_usd=r.min_bet_usd,
        deviation_threshold=r.deviation_threshold,
        min_liquidity_multiple=r.min_liquidity_multiple,
        kelly_fraction=r.kelly_fraction,
        ai_scan_interval_min=s.ai_scan_interval_min,
        price_check_interval_min=s.price_check_interval_min,
        max_markets_per_ai_scan=s.max_markets_per_ai_scan,
        starting_balance_usd=r.starting_balance_usd,
    )


# ── Logging setup ─────────────────────────────────────────────────────────────

def setup_logging(cfg: AppConfig) -> None:
    log_cfg = cfg.logging
    Path(log_cfg.file).parent.mkdir(parents=True, exist_ok=True)

    level = getattr(logging, log_cfg.level.upper(), logging.INFO)
    fmt = "%(asctime)s %(levelname)s %(name)s %(message)s"

    root = logging.getLogger()
    root.setLevel(level)

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(level)
    ch.setFormatter(logging.Formatter(fmt))
    root.addHandler(ch)

    # Rotating file handler
    fh = logging.handlers.RotatingFileHandler(
        log_cfg.file,
        maxBytes=log_cfg.max_size_mb * 1024 * 1024,
        backupCount=log_cfg.backup_count,
    )
    fh.setLevel(level)
    fh.setFormatter(logging.Formatter(fmt))
    root.addHandler(fh)


# ── Bootstrap ─────────────────────────────────────────────────────────────────

def bootstrap(config_path: str = "config.yaml") -> AppConfig:
    from src.agent.notifier import setup_notifier
    cfg = load_config(config_path)
    setup_logging(cfg)
    init_db()
    setup_notifier(cfg.notify.telegram_bot_token, cfg.notify.telegram_chat_id)

    # Ensure portfolio row exists
    p = get_portfolio()
    if p.starting_balance_usd == 500.0 and p.current_balance_usd == 500.0:
        # First run — seed from config
        p.starting_balance_usd = cfg.risk.starting_balance_usd
        p.current_balance_usd = cfg.risk.starting_balance_usd
        update_portfolio(p)

    return cfg


# ── Stop flag ─────────────────────────────────────────────────────────────────

STOP_FLAG = Path("agent.stop")


def should_stop() -> bool:
    return STOP_FLAG.exists()


def clear_stop_flag() -> None:
    STOP_FLAG.unlink(missing_ok=True)


def write_pid() -> None:
    Path("agent.pid").write_text(str(os.getpid()))


def clear_pid() -> None:
    Path("agent.pid").unlink(missing_ok=True)
