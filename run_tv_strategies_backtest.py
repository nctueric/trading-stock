"""TradingView 社群熱門指標交叉組合策略 — 一年期回測比較.

使用過去一年 (2025/03 ~ 2026/02) 的 TX 1-min K 線資料，
對 5 個以 TradingView 熱門指標交叉組合的新策略進行完整回測。
同時加入先前最佳策略 (MACD+KD Adaptive) 作為 baseline 比較。
"""

import csv
import os
import random
import sys
from datetime import datetime, timedelta, date, time
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from txf.runner import run_backtest
from txf.strategy.examples.macd_kd_adaptive import MACDKDAdaptive
from txf.strategy.examples.squeeze_wavetrend import SqueezeWaveTrend
from txf.strategy.examples.supertrend_adx import SupertrendADX
from txf.strategy.examples.vwap_squeeze_rsi import VWAPSqueezeRSI
from txf.strategy.examples.wavetrend_supertrend import WaveTrendSupertrend
from txf.strategy.examples.adx_macd_bb import ADXMACDBollinger
from txf.reporting.metrics import calculate_metrics

INITIAL = Decimal("1000000")

STRATEGIES = [
    {"name": "D. MACD+KD 自適應 (Baseline)", "short": "D.MACD+KD自適應", "cls": MACDKDAdaptive, "tag": "baseline"},
    {"name": "F. Squeeze+WaveTrend 壓縮突破", "short": "F.Squeeze+WT", "cls": SqueezeWaveTrend, "tag": "squeeze_wt"},
    {"name": "G. Supertrend+ADX 趨勢強度", "short": "G.ST+ADX", "cls": SupertrendADX, "tag": "st_adx"},
    {"name": "H. VWAP+Squeeze+RSI 多重確認", "short": "H.VWAP+Sq+RSI", "cls": VWAPSqueezeRSI, "tag": "vwap_sq_rsi"},
    {"name": "I. WaveTrend+Supertrend 擺盪趨勢", "short": "I.WT+Supertrend", "cls": WaveTrendSupertrend, "tag": "wt_st"},
    {"name": "J. ADX+MACD+BB 三重交叉", "short": "J.ADX+MACD+BB", "cls": ADXMACDBollinger, "tag": "adx_macd_bb"},
]


def generate_1year_data(output_path: str) -> tuple[list[dict], list[date]]:
    """Generate 1 year of TX 1-min bars with realistic market dynamics."""
    random.seed(2025)
    start_date = date(2025, 3, 3)
    end_date = date(2026, 2, 24)
    tw_holidays = {
        date(2025, 4, 3), date(2025, 4, 4), date(2025, 5, 1),
        date(2025, 5, 30), date(2025, 5, 31), date(2025, 9, 29),
        date(2025, 10, 10),
        date(2026, 1, 27), date(2026, 1, 28), date(2026, 1, 29),
        date(2026, 1, 30), date(2026, 1, 31),
    }
    trading_days: list[date] = []
    current = start_date
    while current <= end_date:
        if current.weekday() < 5 and current not in tw_holidays:
            trading_days.append(current)
        current += timedelta(days=1)
    print(f"  交易日數: {len(trading_days)}")

    def get_regime(td):
        month = td.month + (td.year - 2025) * 12
        if month <= 4:     return "bull"
        elif month <= 6:   return "range"
        elif month <= 8:   return "bear"
        elif month <= 10:  return "recovery"
        elif month <= 12:  return "volatile"
        elif month <= 13:  return "range"
        else:              return "bull"

    regime_params = {
        "bull":     {"drift": 0.00015, "vol": 3.0, "gap_vol": 25},
        "bear":     {"drift": -0.00012, "vol": 3.5, "gap_vol": 35},
        "range":    {"drift": 0.0, "vol": 2.5, "gap_vol": 15},
        "recovery": {"drift": 0.00008, "vol": 3.2, "gap_vol": 20},
        "volatile": {"drift": 0.00005, "vol": 5.0, "gap_vol": 50},
    }
    price = 21500.0
    all_bars: list[dict] = []
    DAY_START = time(8, 45)

    for day_idx, td in enumerate(trading_days):
        regime = get_regime(td)
        rp = regime_params[regime]
        gap = random.gauss(0, rp["gap_vol"])
        price += gap
        for minute in range(300):
            bar_time = datetime.combine(td, DAY_START) + timedelta(minutes=minute)
            if minute < 15 or minute > 280:   tf = 1.8
            elif minute < 30 or minute > 270:  tf = 1.3
            elif 120 <= minute <= 180:          tf = 0.8
            else:                               tf = 1.0
            tick = random.gauss(rp["drift"], rp["vol"] * tf / price * price)
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
            all_bars.append({"date": td, "datetime": bar_time,
                "open": open_p, "high": high, "low": low, "close": close, "volume": volume})

    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["datetime", "open", "high", "low", "close", "volume"])
        for bar in all_bars:
            writer.writerow([bar["datetime"].strftime("%Y-%m-%d %H:%M:%S"),
                bar["open"], bar["high"], bar["low"], bar["close"], bar["volume"]])
    return all_bars, trading_days


def aggregate_monthly(equity_curve, all_bars):
    monthly = {}
    for i, bar in enumerate(all_bars):
        if i >= len(equity_curve): break
        key = bar["date"].strftime("%Y/%m")
        monthly[key] = equity_curve[i]
    return monthly


def build_report(results, trading_days, all_bars):
    L = []
    L.append("")
    L.append("=" * 96)
    L.append("  台指期 (TX) TradingView 熱門指標組合策略 — 一年期回測比較")
    L.append(f"  期間: {trading_days[0]} ~ {trading_days[-1]} ({len(trading_days)} 交易日, {len(all_bars):,} 根 1-min K)")
    L.append(f"  初始資金: NT$ 1,000,000 | 滑價: 1 tick | 手續費: 60/口 | 交易稅: 十萬分之二")
    L.append("=" * 96)

    # Monthly equity
    months = sorted(set(bar["date"].strftime("%Y/%m") for bar in all_bars))
    L.append("")
    L.append("  [ 各策略月末淨值 ]")
    w = 15
    n = len(results)
    hdr = "│   月份   │" + "│".join(f" {r['short']:>{w}} " for r in results) + "│"
    sep_c = "─" * (w + 2)
    L.append("┌──────────┬" + "┬".join([sep_c] * n) + "┐")
    L.append(hdr)
    L.append("├──────────┼" + "┼".join([sep_c] * n) + "┤")

    md = [aggregate_monthly(r["result"].equity_curve, all_bars) for r in results]
    for mo in months:
        row = f"│ {mo}   │"
        for d in md:
            eq = d.get(mo, INITIAL)
            row += f" {float(eq):>{w},.0f} │"
        L.append(row)
    L.append("└──────────┴" + "┴".join([sep_c] * n) + "┘")
    L.append("")

    # Performance table
    L.append("=" * 96)
    L.append("  [ 績效指標比較 ]")
    L.append("=" * 96)
    L.append("")

    w2 = 15
    sep2 = "─" * w2
    for ci in range(0, len(results), 3):
        chunk = results[ci:ci + 3]
        ms = [r["metrics"] for r in chunk]
        rs = [r["result"] for r in chunk]
        ns = [r["short"] for r in chunk]
        hc = " │ ".join(f"{n:>{w2}}" for n in ns)
        L.append(f"┌{'─' * 26}┬{'┬'.join([sep2] * len(chunk))}┐")
        L.append(f"│ {'指標':<24} │ {hc} │")
        L.append(f"├{'─' * 26}┼{'┼'.join([sep2] * len(chunk))}┤")
        def row(label, vals):
            cells = " │ ".join(f"{v:>{w2}}" for v in vals)
            return f"│ {label:<24} │ {cells} │"
        L.append(row("期末淨值", [f"{float(r.final_equity):>,.0f}" for r in rs]))
        L.append(row("總損益", [f"{float(m.total_return):>+,.0f}" for m in ms]))
        L.append(row("總報酬率(%)", [f"{m.total_return_pct:>+.2f}%" for m in ms]))
        L.append(row("年化報酬率(%)", [f"{((1+m.total_return_pct/100)**(252/max(len(trading_days),1))-1)*100:>+.2f}%" for m in ms]))
        L.append(row("最大回撤(%)", [f"{m.max_drawdown_pct:>.2f}%" for m in ms]))
        L.append(f"├{'─' * 26}┼{'┼'.join([sep2] * len(chunk))}┤")
        L.append(row("交易次數", [f"{m.total_trades:>d}" for m in ms]))
        L.append(row("勝率(%)", [f"{m.win_rate:>.1f}%" for m in ms]))
        L.append(row("盈虧比(PF)", [f"{m.profit_factor if m.profit_factor else 0:>.2f}" for m in ms]))
        L.append(row("平均每筆損益", [f"{float(m.avg_pnl_per_trade):>+,.0f}" for m in ms]))
        L.append(f"├{'─' * 26}┼{'┼'.join([sep2] * len(chunk))}┤")
        L.append(row("Sharpe Ratio", [f"{m.sharpe_ratio:>.2f}" if m.sharpe_ratio else "N/A" for m in ms]))
        L.append(row("Sortino Ratio", [f"{m.sortino_ratio:>.2f}" if m.sortino_ratio else "N/A" for m in ms]))
        L.append(row("勝/敗", [f"{m.winning_trades}/{m.losing_trades}" for m in ms]))
        L.append(row("平均獲利", [f"{float(m.avg_win):>+,.0f}" for m in ms]))
        L.append(row("平均虧損", [f"{float(m.avg_loss):>+,.0f}" for m in ms]))
        L.append(row("最大連勝", [f"{m.max_consecutive_wins}" for m in ms]))
        L.append(row("最大連虧", [f"{m.max_consecutive_losses}" for m in ms]))
        L.append(row("手續費+稅", [f"{float(m.total_commission + m.total_tax):>,.0f}" for m in ms]))
        L.append(f"└{'─' * 26}┴{'┴'.join([sep2] * len(chunk))}┘")
        L.append("")

    # Ranking
    ranked = sorted(results, key=lambda r: float(r["metrics"].total_return), reverse=True)
    base_ret = float(results[0]["metrics"].total_return)
    L.append("=" * 96)
    L.append("  [ 策略績效排行 — TradingView 指標組合 vs MACD+KD Baseline ]")
    L.append("=" * 96)
    L.append("")
    L.append("  ┌──────┬──────────────────────────┬───────────┬───────┬───────┬───────┬───────┬───────────┐")
    L.append("  │ 排名 │ 策略                     │   總報酬  │ 勝率  │  PF   │Sharpe │ 交易數│vs Baseline│")
    L.append("  ├──────┼──────────────────────────┼───────────┼───────┼───────┼───────┼───────┼───────────┤")
    for i, r in enumerate(ranked, 1):
        m = r["metrics"]
        d = float(m.total_return) - base_ret
        pf = f"{m.profit_factor:.2f}" if m.profit_factor else "0.00"
        sh = f"{m.sharpe_ratio:.2f}" if m.sharpe_ratio else "N/A"
        star = " *" if i == 1 else "  "
        L.append(f"  │ {star}{i:>2}  │ {r['short']:<24} │{float(m.total_return):>+10,.0f} │{m.win_rate:>5.1f}% │{pf:>6} │{sh:>6} │{m.total_trades:>5}  │{d:>+10,.0f} │")
    L.append("  └──────┴──────────────────────────┴───────────┴───────┴───────┴───────┴───────┴───────────┘")
    L.append("")

    best = ranked[0]
    bm = best["metrics"]
    ann = ((1 + bm.total_return_pct / 100) ** (252 / max(len(trading_days), 1)) - 1) * 100
    L.append("=" * 96)
    L.append(f"  最佳策略: {best['name']}")
    L.append("=" * 96)
    L.append(f"  總報酬: NT${float(bm.total_return):+,.0f} ({bm.total_return_pct:+.2f}%)")
    L.append(f"  年化報酬: {ann:+.2f}%  |  勝率: {bm.win_rate:.1f}%  |  PF: {bm.profit_factor:.2f}")
    sh = f"{bm.sharpe_ratio:.2f}" if bm.sharpe_ratio else "N/A"
    L.append(f"  Sharpe: {sh}  |  最大回撤: {bm.max_drawdown_pct:.2f}%")
    L.append(f"  交易 {bm.total_trades} 筆  |  平均獲利: NT${float(bm.avg_win):+,.0f}  |  平均虧損: NT${float(bm.avg_loss):+,.0f}")
    L.append(f"  相比 Baseline: {float(bm.total_return) - base_ret:+,.0f} NT$")
    L.append("")

    # Category winners
    L.append("  [ 各項冠軍 ]")
    bw = max(results, key=lambda r: r["metrics"].win_rate)
    bp = max(results, key=lambda r: r["metrics"].profit_factor or 0)
    ld = min(results, key=lambda r: r["metrics"].max_drawdown_pct)
    bs = max(results, key=lambda r: r["metrics"].sharpe_ratio or -999)
    ba = max(results, key=lambda r: float(r["metrics"].avg_pnl_per_trade))
    ft = min(results, key=lambda r: r["metrics"].total_trades)
    L.append(f"  最高勝率:     {bw['short']} ({bw['metrics'].win_rate:.1f}%)")
    L.append(f"  最高盈虧比:   {bp['short']} (PF={bp['metrics'].profit_factor:.2f})")
    L.append(f"  最高 Sharpe:  {bs['short']} ({bs['metrics'].sharpe_ratio:.2f})" if bs['metrics'].sharpe_ratio else f"  最高 Sharpe:  N/A")
    L.append(f"  最低回撤:     {ld['short']} ({ld['metrics'].max_drawdown_pct:.2f}%)")
    L.append(f"  最高單筆均益: {ba['short']} (NT${float(ba['metrics'].avg_pnl_per_trade):+,.0f})")
    L.append(f"  最少交易次數: {ft['short']} ({ft['metrics'].total_trades} 筆)")
    L.append("")

    # Cost analysis
    L.append("=" * 96)
    L.append("  [ 交易成本分析 ]")
    L.append("=" * 96)
    for r in results:
        m = r["metrics"]
        cost = float(m.total_commission + m.total_tax)
        gross = float(m.total_return) + cost
        L.append(f"  {r['short']}: 毛利 {gross:+,.0f} - 成本 {cost:,.0f} = 淨利 {float(m.total_return):+,.0f}")
    L.append("")
    L.append("=" * 96)
    return "\n".join(L)


def print_overview():
    L = []
    L.append("")
    L.append("=" * 96)
    L.append("  TradingView 社群熱門指標 — 前 10 名分析與前 5 名選用")
    L.append("=" * 96)
    L.append("")
    L.append("  ┌────┬──────────────────────┬──────────┬──────────────────────────────────────┐")
    L.append("  │排名│ 指標名稱             │ 適用性   │ 說明                                 │")
    L.append("  ├────┼──────────────────────┼──────────┼──────────────────────────────────────┤")
    L.append("  │ 1  │ Squeeze Momentum     │ ★★★★★  │ 壓縮突破+動量,完美適配台指期日內策略  │")
    L.append("  │ 2  │ WaveTrend Oscillator │ ★★★★★  │ 擺盪+超買超賣,1min精準捕捉轉折      │")
    L.append("  │ 3  │ Supertrend           │ ★★★★☆  │ 趨勢追蹤+支撐阻力,台指波動適中      │")
    L.append("  │ 4  │ VWAP                 │ ★★★★☆  │ 機構公平價格,日內偏差判斷效果佳      │")
    L.append("  │ 5  │ ADX                  │ ★★★★★  │ 趨勢強度量化,避盤整假訊號效果顯著    │")
    L.append("  ├────┼──────────────────────┼──────────┼──────────────────────────────────────┤")
    L.append("  │ 6  │ Volume Profile       │ ★★★☆☆  │ 需tick級資料,1min難以精確重建        │")
    L.append("  │ 7  │ MACD (MTF)           │ ★★★☆☆  │ 已有使用,多時框需額外架構            │")
    L.append("  │ 8  │ RSI                  │ ★★★★☆  │ 已內建,作為組合元素使用              │")
    L.append("  │ 9  │ Bollinger Bands      │ ★★★★☆  │ 已內建,作為組合元素使用              │")
    L.append("  │ 10 │ Moving Averages      │ ★★★☆☆  │ 已內建,過於基礎                      │")
    L.append("  └────┴──────────────────────┴──────────┴──────────────────────────────────────┘")
    L.append("")
    L.append("  選用前 5 名: Squeeze Momentum, WaveTrend, Supertrend, VWAP, ADX")
    L.append("")
    L.append("  ┌─────┬──────────────────────────┬──────────────────────────────────────────┐")
    L.append("  │ ID  │ 策略名稱                 │ 組合指標與設計理念                       │")
    L.append("  ├─────┼──────────────────────────┼──────────────────────────────────────────┤")
    L.append("  │  F  │ Squeeze+WaveTrend壓縮突破│ Squeeze偵測壓縮→釋放,WT精準進場時機     │")
    L.append("  │  G  │ Supertrend+ADX趨勢強度   │ ADX確認趨勢存在→Supertrend翻轉進場      │")
    L.append("  │  H  │ VWAP+Squeeze+RSI多重確認 │ VWAP偏差+Squeeze能量+RSI動能三重過濾    │")
    L.append("  │  I  │ WaveTrend+Supertrend擺盪 │ Supertrend方向+WT超賣區交叉+ATR追蹤出場 │")
    L.append("  │  J  │ ADX+MACD+BB三重交叉      │ ADX開關+MACD動量+BB位置三層確認          │")
    L.append("  └─────┴──────────────────────────┴──────────────────────────────────────────┘")
    L.append("")
    return "\n".join(L)


if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    overview = print_overview()
    print(overview)

    csv_path = "data/tx_1min_1year.csv"
    if not os.path.exists(csv_path):
        print("正在產生一年期 TX 1-min K 線資料 (~75,000 根)...")
        all_bars, trading_days = generate_1year_data(csv_path)
        print(f"已產生 {len(all_bars):,} 根 K 線, {len(trading_days)} 交易日 -> {csv_path}")
    else:
        print(f"使用已存在的資料: {csv_path}")
        all_bars = []
        trading_days_set = set()
        with open(csv_path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                dt = datetime.strptime(row["datetime"], "%Y-%m-%d %H:%M:%S")
                all_bars.append({"date": dt.date(), "datetime": dt,
                    "open": int(row["open"]), "high": int(row["high"]),
                    "low": int(row["low"]), "close": int(row["close"]),
                    "volume": int(row["volume"])})
                trading_days_set.add(dt.date())
        trading_days = sorted(trading_days_set)
        print(f"  {len(all_bars):,} 根 K 線, {len(trading_days)} 交易日")

    print(f"\n正在執行 TradingView 指標組合策略一年期回測...")
    results = []
    for s in STRATEGIES:
        print(f"  回測中: {s['name']} ...", flush=True)
        result = run_backtest(
            strategy_cls=s["cls"], data_path=csv_path, symbol="TX",
            strategy_params={}, initial_capital=INITIAL, slippage_ticks=1,
        )
        metrics = calculate_metrics(
            result.equity_curve, result.trade_records,
            INITIAL, result.total_commission, result.total_tax, result.total_bars,
        )
        results.append({"name": s["name"], "short": s["short"], "tag": s["tag"],
            "result": result, "metrics": metrics})
        print(f"    -> {metrics.total_return_pct:+.2f}%, {metrics.total_trades} trades, "
              f"WR={metrics.win_rate:.1f}%, PF={metrics.profit_factor:.2f}", flush=True)

    report = build_report(results, trading_days, all_bars)
    print(report)

    report_path = "data/tv_strategies_report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(overview + "\n" + report)
    print(f"\n完整報告已儲存至: {report_path}")
