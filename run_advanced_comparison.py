"""MACD+KD 衍生策略比較回測.

以原始 MACD+KD 為基準，比較 5 個衍生策略的績效。
"""

import os
import sys
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

DATA_PATH = "data/tx_1min_202601_202602.csv"
if not os.path.exists(DATA_PATH):
    print("請先執行 run_backtest_report.py 產生資料")
    sys.exit(1)

INITIAL = Decimal("1000000")

STRATEGIES = [
    {
        "name": "④ 原始 MACD+KD 共振 (Baseline)",
        "short": "④ 原始MACD+KD",
        "cls": MACDKDConfluence,
        "params": {},
        "tag": "baseline",
    },
    {
        "name": "A. MACD+KD + ATR 動態追蹤停損",
        "short": "A. ATR追蹤停損",
        "cls": MACDKDTrailingATR,
        "params": {},
        "tag": "trailing",
    },
    {
        "name": "B. MACD+KD + 成交量確認",
        "short": "B. 成交量確認",
        "cls": MACDKDVolume,
        "params": {},
        "tag": "volume",
    },
    {
        "name": "C. MACD+KD + RSI 動能過濾",
        "short": "C. RSI動能過濾",
        "cls": MACDKDRSIFilter,
        "params": {},
        "tag": "rsi",
    },
    {
        "name": "D. MACD+KD 自適應波動率",
        "short": "D. 自適應波動率",
        "cls": MACDKDAdaptive,
        "params": {},
        "tag": "adaptive",
    },
    {
        "name": "E. MACD+KD + 布林通道位置",
        "short": "E. 布林位置評估",
        "cls": MACDKDBollinger,
        "params": {},
        "tag": "bollinger",
    },
]


def run_all():
    results = []
    for s in STRATEGIES:
        print(f"  回測中: {s['name']} ...")
        result = run_backtest(
            strategy_cls=s["cls"],
            data_path=DATA_PATH,
            symbol="TX",
            strategy_params=s["params"],
            initial_capital=INITIAL,
            slippage_ticks=1,
        )
        metrics = calculate_metrics(
            result.equity_curve, result.trade_records,
            INITIAL, result.total_commission, result.total_tax, result.total_bars,
        )
        results.append({"name": s["name"], "short": s["short"], "tag": s["tag"],
                        "result": result, "metrics": metrics})
    return results


def print_design_rationale():
    lines = []
    lines.append("")
    lines.append("=" * 92)
    lines.append("  MACD+KD 共振策略 — 五大衍生策略設計理念")
    lines.append("=" * 92)
    lines.append("")
    lines.append("  原始 MACD+KD 優勢: 三重確認 (趨勢EMA + 動能MACD + 擺盪KD) → 75.8% 勝率")
    lines.append("  但仍有改良空間，以下針對不同面向各設計一個衍生策略：")
    lines.append("")
    lines.append("  ┌─────┬─────────────────────┬──────────────────────────────────────────────────┐")
    lines.append("  │ ID  │ 策略名稱            │ 改良方向                                         │")
    lines.append("  ├─────┼─────────────────────┼──────────────────────────────────────────────────┤")
    lines.append("  │  A  │ ATR 動態追蹤停損    │ 固定停損→ATR倍數動態停損+追蹤停利讓利潤奔跑      │")
    lines.append("  │  B  │ 成交量確認          │ 進場需放量確認+量價背離提前出場                   │")
    lines.append("  │  C  │ RSI 動能過濾        │ RSI 避免超買追多/超賣追空+交叉窗口放寬            │")
    lines.append("  │  D  │ 自適應波動率        │ 高波動→寬SL/TP, 低波動→窄SL/TP或不交易           │")
    lines.append("  │  E  │ 布林通道位置評估    │ 避免追高/追低+布林帶觸及出場+持倉時間限制         │")
    lines.append("  └─────┴─────────────────────┴──────────────────────────────────────────────────┘")
    lines.append("")
    lines.append("  ─── 各策略詳細說明 ─────────────────────────────────────────────────────────")
    lines.append("")
    lines.append("  A. ATR 動態追蹤停損:")
    lines.append("     • 停損 = 進場價 ± 2.0×ATR (波動大→空間大, 波動小→精準停損)")
    lines.append("     • 浮盈超過 1.5×ATR 後啟動追蹤停損 (trailing distance = 1.0×ATR)")
    lines.append("     • 讓獲利單持續奔跑, 而非固定 50 點就了結")
    lines.append("")
    lines.append("  B. 成交量確認:")
    lines.append("     • 進場: 成交量 > 20期均量 × 1.2 (有量才是真突破)")
    lines.append("     • 出場: 連續 3 根量遞減 + 有浮盈 → 量能衰退提前了結")
    lines.append("     • 目的: 過濾量縮時的假訊號")
    lines.append("")
    lines.append("  C. RSI 動能過濾:")
    lines.append("     • 做多需 RSI 在 40-65 (不在超買區追高)")
    lines.append("     • 做空需 RSI 在 35-60 (不在超賣區追低)")
    lines.append("     • MACD 和 KD 交叉允許 3 根 K 線窗口 (不需同 bar 出現)")
    lines.append("     • KD 到極端區 (>80/<20) 直接出場")
    lines.append("")
    lines.append("  D. 自適應波動率:")
    lines.append("     • ATR 低於 25 percentile → 不開新倉 (避免量縮假訊號)")
    lines.append("     • ATR 25-75th → 標準 SL=30/TP=50")
    lines.append("     • ATR 高於 75th → 放寬 SL=40/TP=65 (給價格空間)")
    lines.append("")
    lines.append("  E. 布林通道位置評估:")
    lines.append("     • 做多時價格不能已在上軌外 (避免追高)")
    lines.append("     • 觸及對向布林軌道 + 有浮盈 → 獲利了結")
    lines.append("     • 持倉超過 45 根 K 線未達 TP → 市價平倉 (避免盤整耗損)")
    lines.append("")

    return "\n".join(lines)


def print_comparison(results):
    lines = []
    lines.append("=" * 92)
    lines.append("  六策略回測比較 (TX 1-min, 2026/01/19~02/24, 27 交易日, 初始 NT$1,000,000)")
    lines.append("=" * 92)
    lines.append("")

    # Table header
    names = [r["short"] for r in results]
    # Split into two tables for readability (3+3)
    for table_idx, chunk in enumerate([results[:3], results[3:]]):
        ms = [r["metrics"] for r in chunk]
        rs = [r["result"] for r in chunk]
        ns = [r["short"] for r in chunk]

        w = 14  # column width
        sep = "─" * w
        header_cells = " │ ".join(f"{n:>{w}}" for n in ns)
        lines.append(f"┌{'─' * 26}┬{'┬'.join([sep] * 3)}┐")
        lines.append(f"│ {'指標':<24} │ {header_cells} │")
        lines.append(f"├{'─' * 26}┼{'┼'.join([sep] * 3)}┤")

        def row(label, vals):
            cells = " │ ".join(f"{v:>{w}}" for v in vals)
            return f"│ {label:<24} │ {cells} │"

        lines.append(row("期末淨值", [f"{float(r.final_equity):>,.0f}" for r in rs]))
        lines.append(row("總損益", [f"{float(m.total_return):>+,.0f}" for m in ms]))
        lines.append(row("總報酬率(%)", [f"{m.total_return_pct:>+.2f}%" for m in ms]))
        lines.append(row("最大回撤(%)", [f"{m.max_drawdown_pct:>.2f}%" for m in ms]))
        lines.append(f"├{'─' * 26}┼{'┼'.join([sep] * 3)}┤")
        lines.append(row("交易次數", [f"{m.total_trades:>d}" for m in ms]))
        lines.append(row("勝率(%)", [f"{m.win_rate:>.1f}%" for m in ms]))
        lines.append(row("盈虧比(PF)", [f"{m.profit_factor if m.profit_factor else 0:>.2f}" for m in ms]))
        lines.append(row("平均每筆損益", [f"{float(m.avg_pnl_per_trade):>+,.0f}" for m in ms]))
        lines.append(f"├{'─' * 26}┼{'┼'.join([sep] * 3)}┤")
        sharpes = [f"{m.sharpe_ratio:>.2f}" if m.sharpe_ratio else "N/A" for m in ms]
        lines.append(row("Sharpe Ratio", sharpes))
        lines.append(row("勝 / 敗", [f"{m.winning_trades}/{m.losing_trades}" for m in ms]))
        lines.append(row("平均獲利", [f"{float(m.avg_win):>+,.0f}" for m in ms]))
        lines.append(row("平均虧損", [f"{float(m.avg_loss):>+,.0f}" for m in ms]))
        lines.append(row("最大連續虧損", [f"{m.max_consecutive_losses}" for m in ms]))
        lines.append(row("手續費+稅", [f"{float(m.total_commission + m.total_tax):>,.0f}" for m in ms]))
        lines.append(f"└{'─' * 26}┴{'┴'.join([sep] * 3)}┘")
        lines.append("")

    # Ranking
    ranked = sorted(results, key=lambda r: float(r["metrics"].total_return), reverse=True)
    baseline_ret = float(results[0]["metrics"].total_return)

    lines.append("=" * 92)
    lines.append("  策略績效排行 (由最佳到最差)")
    lines.append("=" * 92)
    lines.append("")
    lines.append("  ┌──────┬───────────────────────┬──────────┬───────┬───────┬───────┬──────────┐")
    lines.append("  │ 排名 │ 策略                  │  總報酬  │ 勝率  │  PF   │ 交易數│vs Baseline│")
    lines.append("  ├──────┼───────────────────────┼──────────┼───────┼───────┼───────┼──────────┤")

    for i, r in enumerate(ranked, 1):
        m = r["metrics"]
        delta = float(m.total_return) - baseline_ret
        medal = "🏆" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "  "
        pf_str = f"{m.profit_factor:.2f}" if m.profit_factor else "0.00"
        lines.append(
            f"  │  {medal}{i}  "
            f"│ {r['short']:<21} "
            f"│{float(m.total_return):>+9,.0f} "
            f"│{m.win_rate:>5.1f}% "
            f"│{pf_str:>6} "
            f"│{m.total_trades:>5}  "
            f"│{delta:>+9,.0f} │"
        )

    lines.append("  └──────┴───────────────────────┴──────────┴───────┴───────┴───────┴──────────┘")
    lines.append("")

    # Winner analysis
    best = ranked[0]
    bm = best["metrics"]
    lines.append("=" * 92)
    lines.append(f"  最佳策略: {best['name']}")
    lines.append("=" * 92)
    lines.append(f"  報酬: {bm.total_return_pct:+.2f}%  |  勝率: {bm.win_rate:.1f}%  |  "
                 f"PF: {bm.profit_factor:.2f}  |  Sharpe: {bm.sharpe_ratio:.2f}")
    lines.append(f"  交易 {bm.total_trades} 筆  |  最大回撤: {bm.max_drawdown_pct:.2f}%  |  "
                 f"最大連續虧損: {bm.max_consecutive_losses}")
    delta_vs_base = float(bm.total_return) - baseline_ret
    lines.append(f"  相比原始 MACD+KD: {delta_vs_base:+,.0f} NT$")
    lines.append("")

    # Insights
    lines.append("  [ 分析與結論 ]")
    lines.append("")

    # Find best in each category
    best_wr = max(results, key=lambda r: r["metrics"].win_rate)
    best_pf = max(results, key=lambda r: r["metrics"].profit_factor or 0)
    lowest_dd = min(results, key=lambda r: r["metrics"].max_drawdown_pct)
    fewest_trades = min(results, key=lambda r: r["metrics"].total_trades)
    best_avg = max(results, key=lambda r: float(r["metrics"].avg_pnl_per_trade))

    lines.append(f"  最高勝率:     {best_wr['short']} ({best_wr['metrics'].win_rate:.1f}%)")
    lines.append(f"  最高盈虧比:   {best_pf['short']} (PF={best_pf['metrics'].profit_factor:.2f})")
    lines.append(f"  最低回撤:     {lowest_dd['short']} ({lowest_dd['metrics'].max_drawdown_pct:.2f}%)")
    lines.append(f"  最少交易:     {fewest_trades['short']} ({fewest_trades['metrics'].total_trades} 筆)")
    lines.append(f"  最高單筆均益: {best_avg['short']} (NT${float(best_avg['metrics'].avg_pnl_per_trade):+,.0f})")
    lines.append("")
    lines.append("=" * 92)

    return "\n".join(lines)


if __name__ == "__main__":
    # 1. Print design
    design = print_design_rationale()
    print(design)

    # 2. Run
    print("正在執行六策略比較回測 (含原始 MACD+KD baseline)...")
    results = run_all()

    # 3. Print comparison
    comparison = print_comparison(results)
    print(comparison)

    # 4. Save
    report_path = "data/advanced_comparison_report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(design)
        f.write("\n")
        f.write(comparison)
    print(f"\n完整報告已儲存至: {report_path}")

    # 5. Charts
    try:
        from txf.reporting.visualizer import plot_backtest_result
        for r in results:
            path = f"data/chart_adv_{r['tag']}.html"
            plot_backtest_result(
                r["result"].equity_curve, r["result"].trade_records,
                title=r["name"], output_html=path,
            )
            print(f"  圖表: {path}")
    except ImportError:
        print("(plotly 未安裝)")
