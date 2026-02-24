"""台指期 (TX) 過去一個月 1-min K 線回測 + 逐日報表產生器.

以 100 萬 TWD 起始資金，雙均線交叉策略回測，
產出逐日損益報表、交易明細、績效摘要。
"""

import csv
import os
import random
import sys
from collections import defaultdict
from datetime import datetime, timedelta, date, time
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from txf.runner import run_backtest
from txf.strategy.examples.dual_ma import DualMovingAverageCrossover
from txf.reporting.metrics import calculate_metrics, format_metrics


def generate_minute_bars(output_path: str) -> tuple[list[dict], list[date]]:
    """Generate realistic TX 1-minute OHLCV bars for the past month.

    台指期日盤: 08:45 ~ 13:45 (300 分鐘 / 天)
    模擬 2026/01/19 ~ 2026/02/24 的交易日
    價格範圍: ~22000-23000 (近似當前水準)
    """
    random.seed(42)

    end_date = date(2026, 2, 24)
    start_date = date(2026, 1, 19)

    # Collect trading days (skip weekends)
    trading_days: list[date] = []
    current = start_date
    while current <= end_date:
        if current.weekday() < 5:
            trading_days.append(current)
        current += timedelta(days=1)

    # Generate 1-min bars
    price = 22500.0  # starting price
    all_bars: list[dict] = []
    DAY_START = time(8, 45)
    DAY_END = time(13, 45)

    for td in trading_days:
        # Each day: 300 one-minute bars (08:45 ~ 13:44)
        # Overnight gap
        gap = random.gauss(0, 30)
        price += gap

        for minute in range(300):
            bar_time = datetime.combine(td, DAY_START) + timedelta(minutes=minute)

            # Intraday microstructure: higher volatility at open/close
            time_factor = 1.0
            if minute < 15 or minute > 280:
                time_factor = 1.8
            elif minute < 30:
                time_factor = 1.3

            # Random walk
            tick_change = random.gauss(0, 3.5 * time_factor)
            # Mean reversion towards daily VWAP
            mean_revert = (22500 - price) * 0.0001
            price += tick_change + mean_revert
            price = max(price, 20000)  # floor

            close = round(price)
            spread = abs(random.gauss(0, 2.0 * time_factor))
            high = round(price + abs(random.gauss(0, spread)))
            low = round(price - abs(random.gauss(0, spread)))
            open_p = round(price + random.gauss(0, spread * 0.5))

            high = max(high, open_p, close)
            low = min(low, open_p, close)

            volume = max(1, int(random.gauss(150, 80) * time_factor))

            all_bars.append({
                "date": td,
                "datetime": bar_time,
                "open": open_p,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            })

    # Write CSV
    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["datetime", "open", "high", "low", "close", "volume"])
        for bar in all_bars:
            writer.writerow([
                bar["datetime"].strftime("%Y-%m-%d %H:%M:%S"),
                bar["open"],
                bar["high"],
                bar["low"],
                bar["close"],
                bar["volume"],
            ])

    return all_bars, trading_days


def aggregate_daily_equity(equity_curve, all_bars, trading_days):
    """Aggregate minute-level equity into daily snapshots (end-of-day)."""
    # Map each bar to its date, take the last equity of each date
    daily_equity: dict[date, Decimal] = {}
    daily_close: dict[date, int] = {}

    for i, bar in enumerate(all_bars):
        if i >= len(equity_curve):
            break
        daily_equity[bar["date"]] = equity_curve[i]
        daily_close[bar["date"]] = bar["close"]

    return [
        {
            "date": td,
            "equity": daily_equity.get(td, Decimal("1000000")),
            "close": daily_close.get(td, 0),
        }
        for td in trading_days
        if td in daily_equity
    ]


def generate_report(result, all_bars, trading_days) -> str:
    """Generate the full Chinese-language daily report."""
    initial = Decimal("1000000")
    daily = aggregate_daily_equity(result.equity_curve, all_bars, trading_days)

    lines = []
    lines.append("")
    lines.append("=" * 82)
    lines.append("  台指期 (TX) 每日回測報告")
    lines.append("  策略: 雙均線交叉 (MA5/MA20) | 頻率: 1 分鐘 K 線")
    lines.append(f"  期間: {trading_days[0]} ~ {trading_days[-1]} ({len(trading_days)} 交易日)")
    lines.append(f"  初始資金: NT$ 1,000,000 | 滑價: 1 tick | 乘數: 200 TWD/pt")
    lines.append("=" * 82)
    lines.append("")

    # ── Daily P&L table ──
    lines.append("  [ 逐日損益 ]")
    lines.append("┌────────────┬──────────┬───────────┬────────────┬─────────────┬──────────┐")
    lines.append("│    日期    │  收盤價  │ 當日損益  │  累計損益  │  帳戶淨值   │ 報酬率%  │")
    lines.append("├────────────┼──────────┼───────────┼────────────┼─────────────┼──────────┤")

    for i, d in enumerate(daily):
        prev_eq = daily[i - 1]["equity"] if i > 0 else initial
        daily_pnl = d["equity"] - prev_eq
        cum_pnl = d["equity"] - initial
        ret = float(cum_pnl / initial * 100)

        lines.append(
            f"│ {d['date'].strftime('%Y/%m/%d')} "
            f"│ {d['close']:>7,} "
            f"│{float(daily_pnl):>+10,.0f} "
            f"│{float(cum_pnl):>+11,.0f} "
            f"│{float(d['equity']):>12,.0f} "
            f"│{ret:>+7.2f}% │"
        )

    lines.append("└────────────┴──────────┴───────────┴────────────┴─────────────┴──────────┘")
    lines.append("")

    # ── Trade log ──
    lines.append("=" * 82)
    lines.append("  [ 交易明細 ]")
    lines.append("=" * 82)

    if result.trade_records:
        lines.append(
            "┌────┬──────┬─────────────────┬────────┬─────────────────┬────────┬───────────┬────────┐"
        )
        lines.append(
            "│ #  │ 方向 │    進場時間     │ 進場價 │    出場時間     │ 出場價 │ 損益(NT$) │ 手續費 │"
        )
        lines.append(
            "├────┼──────┼─────────────────┼────────┼─────────────────┼────────┼───────────┼────────┤"
        )

        total_pnl = Decimal("0")
        total_cost = Decimal("0")
        wins = 0

        for idx, t in enumerate(result.trade_records, 1):
            side_str = "做多" if t.side.value == "BUY" else "做空"
            entry_dt = t.entry_time.strftime("%m/%d %H:%M")
            exit_dt = t.exit_time.strftime("%m/%d %H:%M")
            pnl_val = float(t.pnl)
            cost = float(t.commission + t.tax)
            total_pnl += t.pnl
            total_cost += t.commission + t.tax
            if t.pnl > 0:
                wins += 1

            lines.append(
                f"│{idx:>3} "
                f"│ {side_str} "
                f"│ {entry_dt:>15} "
                f"│{float(t.entry_price):>7,.0f} "
                f"│ {exit_dt:>15} "
                f"│{float(t.exit_price):>7,.0f} "
                f"│{pnl_val:>+10,.0f} "
                f"│{cost:>7,.0f} │"
            )

        lines.append(
            "└────┴──────┴─────────────────┴────────┴─────────────────┴────────┴───────────┴────────┘"
        )
    else:
        lines.append("  (本期間無完成交易)")
    lines.append("")

    # ── Performance Summary ──
    metrics = calculate_metrics(
        result.equity_curve,
        result.trade_records,
        initial,
        result.total_commission,
        result.total_tax,
        result.total_bars,
    )

    lines.append("=" * 82)
    lines.append("  [ 績效摘要 ]")
    lines.append("=" * 82)
    lines.append(f"  初始資金:          NT$ {float(initial):>12,.0f}")
    lines.append(f"  期末淨值:          NT$ {float(result.final_equity):>12,.0f}")
    lines.append(f"  總損益:            NT$ {float(metrics.total_return):>+12,.0f}")
    lines.append(f"  總報酬率:              {metrics.total_return_pct:>+10.2f} %")
    lines.append(f"  最大回撤:          NT$ {float(metrics.max_drawdown):>12,.0f}")
    lines.append(f"  最大回撤比例:          {metrics.max_drawdown_pct:>10.2f} %")
    if metrics.sharpe_ratio is not None:
        lines.append(f"  Sharpe Ratio:          {metrics.sharpe_ratio:>10.2f}")
    if metrics.sortino_ratio is not None:
        lines.append(f"  Sortino Ratio:         {metrics.sortino_ratio:>10.2f}")
    if metrics.calmar_ratio is not None:
        lines.append(f"  Calmar Ratio:          {metrics.calmar_ratio:>10.2f}")
    lines.append(f"  ---")
    lines.append(f"  總交易次數:            {metrics.total_trades:>10d}")
    lines.append(f"  勝率:                  {metrics.win_rate:>10.1f} %")
    if metrics.profit_factor is not None:
        lines.append(f"  盈虧比 (Profit Factor):{metrics.profit_factor:>10.2f}")
    lines.append(f"  勝場數:                {metrics.winning_trades:>10d}")
    lines.append(f"  敗場數:                {metrics.losing_trades:>10d}")
    lines.append(f"  平均獲利:          NT$ {float(metrics.avg_win):>+12,.0f}")
    lines.append(f"  平均虧損:          NT$ {float(metrics.avg_loss):>+12,.0f}")
    lines.append(f"  平均每筆損益:      NT$ {float(metrics.avg_pnl_per_trade):>+12,.0f}")
    lines.append(f"  最大連續獲利:          {metrics.max_consecutive_wins:>10d} 筆")
    lines.append(f"  最大連續虧損:          {metrics.max_consecutive_losses:>10d} 筆")
    lines.append(f"  ---")
    lines.append(f"  總手續費:          NT$ {float(metrics.total_commission):>12,.0f}")
    lines.append(f"  總交易稅:          NT$ {float(metrics.total_tax):>12,.0f}")
    lines.append(f"  總 K 線數:             {result.total_bars:>10,d}")
    lines.append(f"  交易天數:              {len(trading_days):>10d}")
    lines.append("=" * 82)

    return "\n".join(lines)


if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)

    # 1. Generate 1-minute data
    csv_path = "data/tx_1min_202601_202602.csv"
    print("正在產生台指期 1 分鐘 K 線資料 (~8,100 根)...")
    all_bars, trading_days = generate_minute_bars(csv_path)
    print(f"已產生 {len(all_bars)} 根 1 分鐘 K 線，{len(trading_days)} 交易日 -> {csv_path}")

    # 2. Run backtest
    print("\n正在執行回測 (雙均線策略 MA5/MA20, 1 分鐘 K 線)...")
    result = run_backtest(
        strategy_cls=DualMovingAverageCrossover,
        data_path=csv_path,
        symbol="TX",
        strategy_params={"fast": 5, "slow": 20},
        initial_capital=Decimal("1000000"),
        slippage_ticks=1,
    )

    # 3. Generate + print report
    report = generate_report(result, all_bars, trading_days)
    print(report)

    # Save report
    report_path = "data/backtest_report_202602.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n報表已儲存至: {report_path}")

    # 4. Generate chart
    try:
        from txf.reporting.visualizer import plot_backtest_result

        chart_path = "data/backtest_chart_202602.html"
        plot_backtest_result(
            result.equity_curve,
            result.trade_records,
            title="台指期 雙均線策略回測 MA5/MA20 (2026/01-02)",
            output_html=chart_path,
        )
        print(f"互動圖表已儲存至: {chart_path}")
    except ImportError:
        print("(plotly 未安裝，跳過圖表產生)")
