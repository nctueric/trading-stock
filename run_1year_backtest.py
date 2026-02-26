"""六策略一年期回測比較.

使用過去一年 (2025/03 ~ 2026/02) 的 TX 1-min K 線資料，
對原始 MACD+KD 及 5 個衍生策略進行完整比較。
"""

import csv
import math
import os
import random
import sys
from collections import defaultdict
from datetime import datetime, timedelta, date, time
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from txf.runner import run_backtest
from txf.strategy.examples.macd_kd_confluence import MACDKDConfluence
from txf.strategy.examples.macd_kd_trailing import MACDKDTrailingATR
from txf.strategy.examples.macd_kd_volume import MACDKDVolume
from txf.strategy.examples.macd_kd_rsi import MACDKDRSIFilter
from txf.strategy.examples.macd_kd_adaptive import MACDKDAdaptive
from txf.strategy.examples.macd_kd_bollinger import MACDKDBollinger
from txf.reporting.metrics import calculate_metrics

INITIAL = Decimal("1000000")

STRATEGIES = [
    {"name": "④ 原始 MACD+KD", "short": "④原始MACD+KD", "cls": MACDKDConfluence, "params": {}, "tag": "baseline"},
    {"name": "A. ATR追蹤停損",  "short": "A.ATR追蹤停損", "cls": MACDKDTrailingATR, "params": {}, "tag": "trailing"},
    {"name": "B. 成交量確認",   "short": "B.成交量確認",  "cls": MACDKDVolume,      "params": {}, "tag": "volume"},
    {"name": "C. RSI動能過濾",  "short": "C.RSI動能過濾", "cls": MACDKDRSIFilter,   "params": {}, "tag": "rsi"},
    {"name": "D. 自適應波動率", "short": "D.自適應波動率","cls": MACDKDAdaptive,    "params": {}, "tag": "adaptive"},
    {"name": "E. 布林位置評估", "short": "E.布林位置評估","cls": MACDKDBollinger,   "params": {}, "tag": "bollinger"},
]


# ──────────────────────────────────────────────────────────────────
#  1-year realistic data generation
# ──────────────────────────────────────────────────────────────────

def generate_1year_data(output_path: str) -> tuple[list[dict], list[date]]:
    """Generate 1 year of TX 1-min bars with realistic market dynamics.

    Simulates multiple market regimes:
    - Trending up (bull)
    - Trending down (bear)
    - Range-bound (choppy)
    - High volatility spikes

    Period: 2025/03/03 ~ 2026/02/24
    ~252 trading days × 300 bars = ~75,600 bars
    """
    random.seed(2025)

    start_date = date(2025, 3, 3)
    end_date = date(2026, 2, 24)

    # Taiwan holidays (approximate major ones)
    tw_holidays = {
        date(2025, 4, 3), date(2025, 4, 4),   # 清明
        date(2025, 5, 1),                       # 勞動節
        date(2025, 5, 30), date(2025, 5, 31),  # 端午
        date(2025, 9, 29),                      # 中秋
        date(2025, 10, 10),                     # 國慶
        date(2026, 1, 27), date(2026, 1, 28), date(2026, 1, 29),
        date(2026, 1, 30), date(2026, 1, 31),  # 農曆新年
    }

    trading_days: list[date] = []
    current = start_date
    while current <= end_date:
        if current.weekday() < 5 and current not in tw_holidays:
            trading_days.append(current)
        current += timedelta(days=1)

    print(f"  交易日數: {len(trading_days)}")

    # Market regime schedule (approximate)
    def get_regime(td: date) -> str:
        month = td.month + (td.year - 2025) * 12
        if month <= 4:     return "bull"       # Mar-Apr 2025: bull
        elif month <= 6:   return "range"      # May-Jun 2025: range
        elif month <= 8:   return "bear"       # Jul-Aug 2025: bear
        elif month <= 10:  return "recovery"   # Sep-Oct 2025: recovery
        elif month <= 12:  return "volatile"   # Nov-Dec 2025: volatile
        elif month <= 13:  return "range"      # Jan 2026: range
        else:              return "bull"        # Feb 2026: bull

    regime_params = {
        "bull":     {"drift": 0.00015, "vol": 3.0, "gap_vol": 25},
        "bear":     {"drift": -0.00012, "vol": 3.5, "gap_vol": 35},
        "range":    {"drift": 0.0, "vol": 2.5, "gap_vol": 15},
        "recovery": {"drift": 0.00008, "vol": 3.2, "gap_vol": 20},
        "volatile": {"drift": 0.00005, "vol": 5.0, "gap_vol": 50},
    }

    price = 21500.0  # Starting price (Mar 2025)
    all_bars: list[dict] = []
    DAY_START = time(8, 45)

    for day_idx, td in enumerate(trading_days):
        regime = get_regime(td)
        rp = regime_params[regime]

        # Overnight gap
        gap = random.gauss(0, rp["gap_vol"])
        price += gap

        # Intraday pattern: U-shape volatility (high at open/close)
        for minute in range(300):
            bar_time = datetime.combine(td, DAY_START) + timedelta(minutes=minute)

            # Time-of-day volatility factor
            if minute < 15 or minute > 280:
                tf = 1.8
            elif minute < 30 or minute > 270:
                tf = 1.3
            elif 120 <= minute <= 180:
                tf = 0.8  # lunch lull
            else:
                tf = 1.0

            # Price movement
            tick = random.gauss(rp["drift"], rp["vol"] * tf / price * price)
            # Mean reversion (long-term anchor drifts with trend)
            anchor = 21500 + day_idx * rp["drift"] * 300
            mean_rev = (anchor - price) * 0.00003
            price += tick + mean_rev
            price = max(price, 18000)
            price = min(price, 26000)

            close = round(price)
            spread = abs(random.gauss(0, 1.5 * tf))
            high = round(price + abs(random.gauss(0, spread)))
            low = round(price - abs(random.gauss(0, spread)))
            open_p = round(price + random.gauss(0, spread * 0.5))
            high = max(high, open_p, close)
            low = min(low, open_p, close)

            vol_base = 180 if regime != "volatile" else 280
            volume = max(1, int(random.gauss(vol_base, 90) * tf))

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
                bar["open"], bar["high"], bar["low"], bar["close"], bar["volume"],
            ])

    return all_bars, trading_days


# ──────────────────────────────────────────────────────────────────
#  Report generation
# ──────────────────────────────────────────────────────────────────

def aggregate_monthly_equity(equity_curve, all_bars) -> dict[str, Decimal]:
    """Aggregate equity to month-end snapshots."""
    monthly: dict[str, Decimal] = {}
    for i, bar in enumerate(all_bars):
        if i >= len(equity_curve):
            break
        key = bar["date"].strftime("%Y/%m")
        monthly[key] = equity_curve[i]
    return monthly


def build_report(results, trading_days, all_bars):
    lines = []
    lines.append("")
    lines.append("=" * 94)
    lines.append("  台指期 (TX) 六策略一年期回測比較")
    lines.append(f"  期間: {trading_days[0]} ~ {trading_days[-1]} ({len(trading_days)} 交易日, {len(all_bars):,} 根 1-min K)")
    lines.append(f"  初始資金: NT$ 1,000,000 | 滑價: 1 tick | 手續費: 60/口 | 交易稅: 十萬分之二")
    lines.append("=" * 94)
    lines.append("")

    # ── Monthly equity table ──
    months_set = sorted(set(bar["date"].strftime("%Y/%m") for bar in all_bars))

    lines.append("  [ 各策略月末淨值 ]")
    hdr = "│   月份   │"
    for r in results:
        hdr += f" {r['short']:>13} │"
    sep_top = "┌──────────┬" + "┬".join(["───────────────"] * len(results)) + "┐"
    sep_mid = "├──────────┼" + "┼".join(["───────────────"] * len(results)) + "┤"
    sep_bot = "└──────────┴" + "┴".join(["───────────────"] * len(results)) + "┘"

    lines.append(sep_top)
    lines.append(hdr)
    lines.append(sep_mid)

    monthly_data = []
    for r in results:
        monthly_data.append(aggregate_monthly_equity(r["result"].equity_curve, all_bars))

    for month in months_set:
        row = f"│ {month}   │"
        for md in monthly_data:
            eq = md.get(month, INITIAL)
            row += f" {float(eq):>12,.0f}  │"
        lines.append(row)

    lines.append(sep_bot)
    lines.append("")

    # ── Main comparison table ──
    lines.append("=" * 94)
    lines.append("  [ 績效指標比較 ]")
    lines.append("=" * 94)
    lines.append("")

    w = 14
    sep = "─" * w

    for chunk_idx in range(0, len(results), 3):
        chunk = results[chunk_idx:chunk_idx + 3]
        ms = [r["metrics"] for r in chunk]
        rs = [r["result"] for r in chunk]
        ns = [r["short"] for r in chunk]

        header_cells = " │ ".join(f"{n:>{w}}" for n in ns)
        lines.append(f"┌{'─' * 26}┬{'┬'.join([sep] * len(chunk))}┐")
        lines.append(f"│ {'指標':<24} │ {header_cells} │")
        lines.append(f"├{'─' * 26}┼{'┼'.join([sep] * len(chunk))}┤")

        def row(label, vals):
            cells = " │ ".join(f"{v:>{w}}" for v in vals)
            return f"│ {label:<24} │ {cells} │"

        lines.append(row("期末淨值", [f"{float(r.final_equity):>,.0f}" for r in rs]))
        lines.append(row("總損益", [f"{float(m.total_return):>+,.0f}" for m in ms]))
        lines.append(row("總報酬率(%)", [f"{m.total_return_pct:>+.2f}%" for m in ms]))
        lines.append(row("年化報酬率(%)", [
            f"{((1 + m.total_return_pct / 100) ** (252 / len(trading_days)) - 1) * 100:>+.2f}%" for m in ms
        ]))
        lines.append(row("最大回撤(%)", [f"{m.max_drawdown_pct:>.2f}%" for m in ms]))
        lines.append(f"├{'─' * 26}┼{'┼'.join([sep] * len(chunk))}┤")
        lines.append(row("交易次數", [f"{m.total_trades:>d}" for m in ms]))
        lines.append(row("勝率(%)", [f"{m.win_rate:>.1f}%" for m in ms]))
        lines.append(row("盈虧比(PF)", [f"{m.profit_factor if m.profit_factor else 0:>.2f}" for m in ms]))
        lines.append(row("平均每筆損益", [f"{float(m.avg_pnl_per_trade):>+,.0f}" for m in ms]))
        lines.append(f"├{'─' * 26}┼{'┼'.join([sep] * len(chunk))}┤")
        sharpes = [f"{m.sharpe_ratio:>.2f}" if m.sharpe_ratio else "N/A" for m in ms]
        sortinos = [f"{m.sortino_ratio:>.2f}" if m.sortino_ratio else "N/A" for m in ms]
        lines.append(row("Sharpe Ratio", sharpes))
        lines.append(row("Sortino Ratio", sortinos))
        lines.append(row("勝 / 敗", [f"{m.winning_trades}/{m.losing_trades}" for m in ms]))
        lines.append(row("平均獲利", [f"{float(m.avg_win):>+,.0f}" for m in ms]))
        lines.append(row("平均虧損", [f"{float(m.avg_loss):>+,.0f}" for m in ms]))
        lines.append(row("最大連勝", [f"{m.max_consecutive_wins}" for m in ms]))
        lines.append(row("最大連虧", [f"{m.max_consecutive_losses}" for m in ms]))
        lines.append(row("手續費+稅", [f"{float(m.total_commission + m.total_tax):>,.0f}" for m in ms]))
        lines.append(f"└{'─' * 26}┴{'┴'.join([sep] * len(chunk))}┘")
        lines.append("")

    # ── Ranking ──
    ranked = sorted(results, key=lambda r: float(r["metrics"].total_return), reverse=True)
    baseline_ret = float(results[0]["metrics"].total_return)

    lines.append("=" * 94)
    lines.append("  [ 策略績效排行 — 一年期 ]")
    lines.append("=" * 94)
    lines.append("")
    lines.append("  ┌──────┬───────────────────┬───────────┬───────┬───────┬───────┬───────┬──────────┐")
    lines.append("  │ 排名 │ 策略              │   總報酬  │ 勝率  │  PF   │Sharpe │ 交易數│vs基準    │")
    lines.append("  ├──────┼───────────────────┼───────────┼───────┼───────┼───────┼───────┼──────────┤")

    for i, r in enumerate(ranked, 1):
        m = r["metrics"]
        delta = float(m.total_return) - baseline_ret
        pf_str = f"{m.profit_factor:.2f}" if m.profit_factor else "0.00"
        sh_str = f"{m.sharpe_ratio:.2f}" if m.sharpe_ratio else "N/A"
        lines.append(
            f"  │  {i:>2}  "
            f"│ {r['short']:<17} "
            f"│{float(m.total_return):>+10,.0f} "
            f"│{m.win_rate:>5.1f}% "
            f"│{pf_str:>6} "
            f"│{sh_str:>6} "
            f"│{m.total_trades:>5}  "
            f"│{delta:>+9,.0f} │"
        )
    lines.append("  └──────┴───────────────────┴───────────┴───────┴───────┴───────┴───────┴──────────┘")
    lines.append("")

    # Winner
    best = ranked[0]
    bm = best["metrics"]
    ann_ret = ((1 + bm.total_return_pct / 100) ** (252 / len(trading_days)) - 1) * 100
    lines.append("=" * 94)
    lines.append(f"  最佳策略: {best['name']}")
    lines.append("=" * 94)
    lines.append(f"  總報酬: NT${float(bm.total_return):+,.0f} ({bm.total_return_pct:+.2f}%)")
    lines.append(f"  年化報酬: {ann_ret:+.2f}%  |  勝率: {bm.win_rate:.1f}%  |  PF: {bm.profit_factor:.2f}")
    lines.append(f"  Sharpe: {bm.sharpe_ratio:.2f}  |  最大回撤: {bm.max_drawdown_pct:.2f}%")
    lines.append(f"  交易 {bm.total_trades} 筆  |  平均獲利: NT${float(bm.avg_win):+,.0f}  |  平均虧損: NT${float(bm.avg_loss):+,.0f}")
    lines.append("")

    # Category winners
    lines.append("  [ 各項冠軍 ]")
    best_wr = max(results, key=lambda r: r["metrics"].win_rate)
    best_pf = max(results, key=lambda r: r["metrics"].profit_factor or 0)
    lowest_dd = min(results, key=lambda r: r["metrics"].max_drawdown_pct)
    best_sharpe = max(results, key=lambda r: r["metrics"].sharpe_ratio or -999)
    best_avg = max(results, key=lambda r: float(r["metrics"].avg_pnl_per_trade))
    lines.append(f"  最高勝率:     {best_wr['short']} ({best_wr['metrics'].win_rate:.1f}%)")
    lines.append(f"  最高盈虧比:   {best_pf['short']} (PF={best_pf['metrics'].profit_factor:.2f})")
    lines.append(f"  最高 Sharpe:  {best_sharpe['short']} ({best_sharpe['metrics'].sharpe_ratio:.2f})")
    lines.append(f"  最低回撤:     {lowest_dd['short']} ({lowest_dd['metrics'].max_drawdown_pct:.2f}%)")
    lines.append(f"  最高單筆均益: {best_avg['short']} (NT${float(best_avg['metrics'].avg_pnl_per_trade):+,.0f})")
    lines.append("")
    lines.append("=" * 94)

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────
#  Main
# ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)

    # 1. Generate data
    csv_path = "data/tx_1min_1year.csv"
    if not os.path.exists(csv_path):
        print("正在產生一年期 TX 1-min K 線資料 (~75,000 根)...")
        all_bars, trading_days = generate_1year_data(csv_path)
        print(f"已產生 {len(all_bars):,} 根 K 線, {len(trading_days)} 交易日 -> {csv_path}")
    else:
        print(f"使用已存在的資料: {csv_path}")
        # Reload bars info
        all_bars = []
        trading_days_set = set()
        with open(csv_path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                dt = datetime.strptime(row["datetime"], "%Y-%m-%d %H:%M:%S")
                all_bars.append({
                    "date": dt.date(),
                    "datetime": dt,
                    "open": int(row["open"]),
                    "high": int(row["high"]),
                    "low": int(row["low"]),
                    "close": int(row["close"]),
                    "volume": int(row["volume"]),
                })
                trading_days_set.add(dt.date())
        trading_days = sorted(trading_days_set)
        print(f"  {len(all_bars):,} 根 K 線, {len(trading_days)} 交易日")

    # 2. Run strategies
    print(f"\n正在執行六策略一年期回測...")
    results = []
    for s in STRATEGIES:
        print(f"  回測中: {s['name']} ...")
        result = run_backtest(
            strategy_cls=s["cls"],
            data_path=csv_path,
            symbol="TX",
            strategy_params=s["params"],
            initial_capital=INITIAL,
            slippage_ticks=1,
        )
        metrics = calculate_metrics(
            result.equity_curve, result.trade_records,
            INITIAL, result.total_commission, result.total_tax, result.total_bars,
        )
        results.append({
            "name": s["name"], "short": s["short"], "tag": s["tag"],
            "result": result, "metrics": metrics,
        })
        print(f"    -> {metrics.total_return_pct:+.2f}%, {metrics.total_trades} trades, "
              f"WR={metrics.win_rate:.1f}%")

    # 3. Report
    report = build_report(results, trading_days, all_bars)
    print(report)

    report_path = "data/1year_comparison_report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n完整報告已儲存至: {report_path}")

    # 4. Charts
    try:
        from txf.reporting.visualizer import plot_backtest_result
        for r in results:
            path = f"data/chart_1yr_{r['tag']}.html"
            plot_backtest_result(
                r["result"].equity_curve, r["result"].trade_records,
                title=f"{r['name']} (一年期)", output_html=path,
            )
            print(f"  圖表: {path}")
    except ImportError:
        print("(plotly 未安裝)")
