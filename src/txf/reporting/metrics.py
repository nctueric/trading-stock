"""Performance metrics calculation for backtest results."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

import numpy as np

from txf.core.types import TradeRecord


@dataclass
class PerformanceMetrics:
    """Comprehensive performance metrics for a backtest."""

    # Return metrics
    total_return: float = 0.0
    total_return_pct: float = 0.0
    annualized_return_pct: float = 0.0

    # Risk metrics
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    annualized_volatility: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0

    # Trade statistics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    avg_pnl_per_trade: float = 0.0
    max_consecutive_losses: int = 0
    max_consecutive_wins: int = 0

    # Futures-specific
    avg_pnl_per_contract: float = 0.0
    total_commission: float = 0.0
    total_tax: float = 0.0

    # Duration
    avg_bars_held: float = 0.0
    total_bars: int = 0


def calculate_metrics(
    equity_curve: list[Decimal],
    trade_records: list[TradeRecord],
    initial_capital: Decimal,
    total_commission: Decimal = Decimal("0"),
    total_tax: Decimal = Decimal("0"),
    total_bars: int = 0,
    bars_per_year: int = 252 * 300,  # ~300 minute bars per day × 252 days
    risk_free_rate: float = 0.02,
) -> PerformanceMetrics:
    """Calculate all performance metrics from backtest results."""
    metrics = PerformanceMetrics()
    metrics.total_bars = total_bars
    metrics.total_commission = float(total_commission)
    metrics.total_tax = float(total_tax)

    if not equity_curve:
        return metrics

    equity = [float(e) for e in equity_curve]
    init_cap = float(initial_capital)

    # -- Return metrics --
    final_equity = equity[-1]
    metrics.total_return = final_equity - init_cap
    metrics.total_return_pct = (
        (metrics.total_return / init_cap * 100) if init_cap > 0 else 0.0
    )

    n_bars = len(equity)
    if n_bars > 1 and bars_per_year > 0 and init_cap > 0:
        total_r = final_equity / init_cap
        years = n_bars / bars_per_year
        if years > 0 and total_r > 0:
            try:
                metrics.annualized_return_pct = (
                    (total_r ** (1.0 / years) - 1.0) * 100
                )
            except (OverflowError, ValueError):
                metrics.annualized_return_pct = 0.0

    # -- Drawdown --
    peak = equity[0]
    max_dd = 0.0
    max_dd_pct = 0.0
    for e in equity:
        if e > peak:
            peak = e
        dd = peak - e
        dd_pct = dd / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct
    metrics.max_drawdown = max_dd
    metrics.max_drawdown_pct = max_dd_pct * 100

    # -- Volatility & Sharpe --
    if n_bars > 1:
        returns = np.diff(equity) / np.array(equity[:-1])
        returns = returns[np.isfinite(returns)]
        if len(returns) > 0:
            vol = float(np.std(returns))
            ann_vol = vol * np.sqrt(bars_per_year)
            metrics.annualized_volatility = ann_vol * 100

            mean_r = float(np.mean(returns))
            rf_per_bar = risk_free_rate / bars_per_year
            if vol > 0:
                metrics.sharpe_ratio = (
                    (mean_r - rf_per_bar) / vol * np.sqrt(bars_per_year)
                )

            # Sortino (downside deviation)
            downside = returns[returns < 0]
            if len(downside) > 0:
                down_vol = float(np.std(downside))
                if down_vol > 0:
                    metrics.sortino_ratio = (
                        (mean_r - rf_per_bar) / down_vol * np.sqrt(bars_per_year)
                    )

    # Calmar
    if max_dd_pct > 0:
        metrics.calmar_ratio = metrics.annualized_return_pct / (max_dd_pct * 100)

    # -- Trade statistics --
    if not trade_records:
        return metrics

    metrics.total_trades = len(trade_records)
    pnls = [float(t.pnl) for t in trade_records]

    winners = [p for p in pnls if p > 0]
    losers = [p for p in pnls if p <= 0]

    metrics.winning_trades = len(winners)
    metrics.losing_trades = len(losers)
    metrics.win_rate = (
        len(winners) / len(pnls) * 100 if pnls else 0.0
    )
    metrics.avg_win = float(np.mean(winners)) if winners else 0.0
    metrics.avg_loss = float(np.mean(losers)) if losers else 0.0
    metrics.avg_pnl_per_trade = float(np.mean(pnls))

    gross_profit = sum(winners)
    gross_loss = abs(sum(losers))
    metrics.profit_factor = (
        gross_profit / gross_loss if gross_loss > 0 else float("inf")
    )

    # Consecutive wins/losses
    metrics.max_consecutive_wins = _max_consecutive(pnls, lambda x: x > 0)
    metrics.max_consecutive_losses = _max_consecutive(pnls, lambda x: x <= 0)

    # Futures-specific
    total_contracts = sum(t.quantity for t in trade_records)
    if total_contracts > 0:
        metrics.avg_pnl_per_contract = sum(pnls) / total_contracts

    # Duration
    bars_held = [t.bars_held for t in trade_records if t.bars_held > 0]
    if bars_held:
        metrics.avg_bars_held = float(np.mean(bars_held))

    return metrics


def _max_consecutive(values: list[float], condition) -> int:
    """Count maximum consecutive items matching a condition."""
    max_count = 0
    current = 0
    for v in values:
        if condition(v):
            current += 1
            max_count = max(max_count, current)
        else:
            current = 0
    return max_count


def format_metrics(m: PerformanceMetrics) -> str:
    """Format metrics as a readable string report."""
    lines = [
        "=" * 50,
        "        BACKTEST PERFORMANCE REPORT",
        "=" * 50,
        "",
        "--- Return ---",
        f"  Total Return:          {m.total_return:>12,.0f} TWD ({m.total_return_pct:>+.2f}%)",
        f"  Annualized Return:     {m.annualized_return_pct:>+12.2f}%",
        "",
        "--- Risk ---",
        f"  Max Drawdown:          {m.max_drawdown:>12,.0f} TWD ({m.max_drawdown_pct:.2f}%)",
        f"  Annualized Volatility: {m.annualized_volatility:>12.2f}%",
        f"  Sharpe Ratio:          {m.sharpe_ratio:>12.2f}",
        f"  Sortino Ratio:         {m.sortino_ratio:>12.2f}",
        f"  Calmar Ratio:          {m.calmar_ratio:>12.2f}",
        "",
        "--- Trades ---",
        f"  Total Trades:          {m.total_trades:>12d}",
        f"  Win Rate:              {m.win_rate:>12.1f}%",
        f"  Profit Factor:         {m.profit_factor:>12.2f}",
        f"  Avg Win:               {m.avg_win:>12,.0f} TWD",
        f"  Avg Loss:              {m.avg_loss:>12,.0f} TWD",
        f"  Avg PnL/Trade:         {m.avg_pnl_per_trade:>12,.0f} TWD",
        f"  Max Consecutive Wins:  {m.max_consecutive_wins:>12d}",
        f"  Max Consecutive Losses:{m.max_consecutive_losses:>12d}",
        "",
        "--- Costs ---",
        f"  Total Commission:      {m.total_commission:>12,.0f} TWD",
        f"  Total Tax:             {m.total_tax:>12,.0f} TWD",
        "",
        "--- Duration ---",
        f"  Total Bars:            {m.total_bars:>12d}",
        f"  Avg Bars Held:         {m.avg_bars_held:>12.1f}",
        "=" * 50,
    ]
    return "\n".join(lines)
