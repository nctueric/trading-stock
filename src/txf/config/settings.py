"""System settings with Pydantic BaseSettings for env var support."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class BacktestSettings(BaseSettings):
    """Settings for a backtest run."""

    initial_capital: Decimal = Decimal("1000000")
    commission_per_contract: Decimal = Decimal("60")
    tax_rate: Decimal = Decimal("0.00002")
    slippage_ticks: int = 1

    model_config = {"env_prefix": "TXF_BT_"}


class RiskSettings(BaseSettings):
    """Risk management parameters."""

    max_position_contracts: int = 10
    max_drawdown_pct: Decimal = Decimal("0.10")
    max_daily_loss: Decimal = Decimal("100000")
    stop_loss_points: Optional[int] = None
    take_profit_points: Optional[int] = None
    trailing_stop_points: Optional[int] = None
    time_stop_bars: Optional[int] = None
    auto_close_before_session_end: bool = False

    model_config = {"env_prefix": "TXF_RISK_"}


class SystemSettings(BaseSettings):
    """Top-level system settings."""

    mode: str = "backtest"  # backtest / paper / live
    data_dir: str = "data"
    log_level: str = "INFO"

    backtest: BacktestSettings = Field(default_factory=BacktestSettings)
    risk: RiskSettings = Field(default_factory=RiskSettings)

    model_config = {"env_prefix": "TXF_"}
