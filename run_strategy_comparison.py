"""三策略比較回測：RSI均值回歸 / 布林壓縮突破 / MACD+KD共振

使用相同的 1 分鐘 K 線資料、相同初始資金，
比較三個改良策略與原始雙均線策略的績效差異。
"""

import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from txf.runner import run_backtest
from txf.strategy.examples.dual_ma import DualMovingAverageCrossover
from txf.strategy.examples.rsi_mean_reversion import RSIMeanReversion
from txf.strategy.examples.bollinger_squeeze import BollingerSqueezeBreakout
from txf.strategy.examples.macd_kd_confluence import MACDKDConfluence
from txf.reporting.metrics import calculate_metrics

# Check data exists
DATA_PATH = "data/tx_1min_202601_202602.csv"
if not os.path.exists(DATA_PATH):
    print("請先執行 run_backtest_report.py 產生資料")
    sys.exit(1)

INITIAL_CAPITAL = Decimal("1000000")
STRATEGIES = [
    {
        "name": "① 原始雙均線 (MA5/MA20)",
        "cls": DualMovingAverageCrossover,
        "params": {"fast": 5, "slow": 20},
        "tag": "baseline",
    },
    {
        "name": "② RSI均值回歸 + ATR過濾",
        "cls": RSIMeanReversion,
        "params": {
            "rsi_period": 14,
            "oversold": 30,
            "overbought": 70,
            "atr_period": 14,
            "cooldown_bars": 10,
            "max_hold_bars": 60,
        },
        "tag": "rsi_mr",
    },
    {
        "name": "③ 布林壓縮突破",
        "cls": BollingerSqueezeBreakout,
        "params": {
            "bb_period": 20,
            "bb_std": 2.0,
            "squeeze_lookback": 50,
            "squeeze_percentile": 25,
            "volume_multiple": 1.3,
            "max_trades_per_day": 3,
        },
        "tag": "bb_squeeze",
    },
    {
        "name": "④ MACD + KD 共振",
        "cls": MACDKDConfluence,
        "params": {
            "macd_fast": 12,
            "macd_slow": 26,
            "macd_signal": 9,
            "kd_k_period": 9,
            "trend_ema_period": 60,
            "stop_loss_points": 30,
            "take_profit_points": 50,
        },
        "tag": "macd_kd",
    },
]


def run_all():
    results = []
    for strat_config in STRATEGIES:
        print(f"  回測中: {strat_config['name']} ...")
        result = run_backtest(
            strategy_cls=strat_config["cls"],
            data_path=DATA_PATH,
            symbol="TX",
            strategy_params=strat_config["params"],
            initial_capital=INITIAL_CAPITAL,
            slippage_ticks=1,
        )
        metrics = calculate_metrics(
            result.equity_curve,
            result.trade_records,
            INITIAL_CAPITAL,
            result.total_commission,
            result.total_tax,
            result.total_bars,
        )
        results.append({
            "name": strat_config["name"],
            "tag": strat_config["tag"],
            "result": result,
            "metrics": metrics,
        })
    return results


def print_analysis():
    """Print strategy weakness analysis before running."""
    lines = []
    lines.append("")
    lines.append("=" * 90)
    lines.append("  現有策略缺陷分析 — 雙均線交叉策略 (MA5/MA20, 1-min K)")
    lines.append("=" * 90)
    lines.append("")
    lines.append("  ┌──────────────────────────────────────────────────────────────────────────────┐")
    lines.append("  │  缺陷 1: 過度交易 (Over-trading)                                            │")
    lines.append("  │  ─────────────────────────────────────────────────                           │")
    lines.append("  │  MA5/MA20 在 1 分鐘圖上交叉極為頻繁 → 27 天產生 103 筆交易                   │")
    lines.append("  │  平均每天 3.8 筆，手續費+稅金合計 NT$ 30,904 (佔虧損 34%)                    │")
    lines.append("  │  → 每次進出場都要付 NT$ 300 成本，小幅盈利被交易成本吃掉                     │")
    lines.append("  │                                                                              │")
    lines.append("  │  缺陷 2: 追漲殺跌 (Trend Chasing in Range Market)                            │")
    lines.append("  │  ─────────────────────────────────────────────────────                       │")
    lines.append("  │  均線交叉屬於「趨勢追蹤」策略，但在 1 分鐘尺度上市場大多震盪                 │")
    lines.append("  │  → 均線黃金交叉做多 → 價格回落 → 死亡交叉做空 → 價格反彈                     │")
    lines.append("  │  → 來回被雙巴 (whipsaw)，勝率僅 27.2%                                       │")
    lines.append("  │                                                                              │")
    lines.append("  │  缺陷 3: 無出場機制 (No Exit Logic)                                          │")
    lines.append("  │  ─────────────────────────────────────────                                   │")
    lines.append("  │  唯一出場方式是等反向交叉 → 沒有停損/停利/時間停損                            │")
    lines.append("  │  → 小虧可能拖成大虧，浮盈也可能全吐回去                                     │")
    lines.append("  │  → Profit Factor 僅 0.60 (每賺 1 元就虧 1.67 元)                             │")
    lines.append("  │                                                                              │")
    lines.append("  │  缺陷 4: 無過濾條件 (No Entry Filter)                                        │")
    lines.append("  │  ───────────────────────────────────────────                                 │")
    lines.append("  │  不管波動率高低、成交量大小，一律進場                                        │")
    lines.append("  │  → 在低波動/假突破時也會發出交叉訊號 → 勝率進一步下降                        │")
    lines.append("  │                                                                              │")
    lines.append("  │  缺陷 5: 單一指標依賴 (Single Indicator)                                     │")
    lines.append("  │  ──────────────────────────────────────────                                  │")
    lines.append("  │  僅靠兩條 SMA 決定進出場，無多指標交叉確認                                   │")
    lines.append("  │  → 假訊號率高，沒有「信號可信度」的分級機制                                  │")
    lines.append("  └──────────────────────────────────────────────────────────────────────────────┘")
    lines.append("")
    lines.append("=" * 90)
    lines.append("  改良策略設計")
    lines.append("=" * 90)
    lines.append("")
    lines.append("  ② RSI 均值回歸 + ATR 波動過濾")
    lines.append("     思路: 逆勢操作 — 超賣(RSI<30)買入、超買(RSI>70)賣出")
    lines.append("     改善: ATR過濾低波動假訊號 + 冷卻期防過度交易 + 持倉時間上限")
    lines.append("")
    lines.append("  ③ 布林通道壓縮突破")
    lines.append("     思路: 等盤整→壓縮→突破，而非隨時進場")
    lines.append("     改善: 成交量確認防假突破 + 中軌動態停損 + 每日交易次數限制")
    lines.append("")
    lines.append("  ④ MACD + KD 多指標共振")
    lines.append("     思路: 趨勢(MACD) + 動能(KD) + 方向(EMA) 三重確認才進場")
    lines.append("     改善: 固定停損30點/停利50點 (R:R=1:1.67) + 時段過濾避開開收盤")
    lines.append("")

    return "\n".join(lines)


def print_comparison(results):
    """Print side-by-side comparison table."""
    lines = []
    lines.append("")
    lines.append("=" * 90)
    lines.append("  四策略回測比較 (同一資料集: TX 1-min, 2026/01/19~02/24, 27 交易日)")
    lines.append("=" * 90)
    lines.append("")

    # Header
    lines.append("┌──────────────────────────┬────────────┬────────────┬────────────┬────────────┐")
    lines.append("│         指標             │  ① 雙均線  │ ② RSI回歸  │ ③ 布林突破 │ ④ MACD+KD  │")
    lines.append("├──────────────────────────┼────────────┼────────────┼────────────┼────────────┤")

    def row(label, values, fmt="{:>10}"):
        cells = " │ ".join(fmt.format(v) for v in values)
        return f"│ {label:<24} │ {cells} │"

    ms = [r["metrics"] for r in results]
    rs = [r["result"] for r in results]

    # Rows
    lines.append(row("期末淨值 (NT$)",
        [f"{float(r.final_equity):>10,.0f}" for r in rs], "{}"))
    lines.append(row("總損益 (NT$)",
        [f"{float(m.total_return):>+10,.0f}" for m in ms], "{}"))
    lines.append(row("總報酬率 (%)",
        [f"{m.total_return_pct:>+10.2f}" for m in ms], "{}"))
    lines.append(row("最大回撤 (%)",
        [f"{m.max_drawdown_pct:>10.2f}" for m in ms], "{}"))

    lines.append("├──────────────────────────┼────────────┼────────────┼────────────┼────────────┤")

    lines.append(row("總交易次數",
        [f"{m.total_trades:>10d}" for m in ms], "{}"))
    lines.append(row("勝率 (%)",
        [f"{m.win_rate:>10.1f}" for m in ms], "{}"))
    lines.append(row("盈虧比 (PF)",
        [f"{m.profit_factor if m.profit_factor else 0:>10.2f}" for m in ms], "{}"))
    lines.append(row("平均每筆損益",
        [f"{float(m.avg_pnl_per_trade):>+10,.0f}" for m in ms], "{}"))

    lines.append("├──────────────────────────┼────────────┼────────────┼────────────┼────────────┤")

    sharpes = [f"{m.sharpe_ratio:>10.2f}" if m.sharpe_ratio else f"{'N/A':>10}" for m in ms]
    lines.append(row("Sharpe Ratio", sharpes, "{}"))
    lines.append(row("勝場 / 敗場",
        [f"{m.winning_trades:>4d} / {m.losing_trades:<4d}" for m in ms], "{}"))
    lines.append(row("平均獲利",
        [f"{float(m.avg_win):>+10,.0f}" for m in ms], "{}"))
    lines.append(row("平均虧損",
        [f"{float(m.avg_loss):>+10,.0f}" for m in ms], "{}"))
    lines.append(row("最大連續虧損",
        [f"{m.max_consecutive_losses:>10d}" for m in ms], "{}"))

    lines.append("├──────────────────────────┼────────────┼────────────┼────────────┼────────────┤")

    lines.append(row("手續費+稅 (NT$)",
        [f"{float(m.total_commission + m.total_tax):>10,.0f}" for m in ms], "{}"))

    lines.append("└──────────────────────────┴────────────┴────────────┴────────────┴────────────┘")
    lines.append("")

    # Winner analysis
    best_idx = max(range(len(ms)), key=lambda i: float(ms[i].total_return))
    best = results[best_idx]
    bm = best["metrics"]

    lines.append("=" * 90)
    lines.append(f"  最佳策略: {best['name']}")
    lines.append("=" * 90)
    lines.append(f"  總報酬: {bm.total_return_pct:+.2f}%  |  勝率: {bm.win_rate:.1f}%  |  "
                 f"交易次數: {bm.total_trades}  |  最大回撤: {bm.max_drawdown_pct:.2f}%")

    baseline = ms[0]
    improvement = float(bm.total_return - baseline.total_return)
    lines.append(f"  相比原始雙均線改善: NT$ {improvement:+,.0f}")
    lines.append("")

    # Key takeaways
    lines.append("  [ 策略改進重點 ]")
    for r in results[1:]:
        m = r["metrics"]
        delta = float(m.total_return - baseline.total_return)
        trade_reduction = baseline.total_trades - m.total_trades
        lines.append(f"  {r['name']}:")
        lines.append(f"    損益變化: NT${delta:+,.0f}  |  交易減少: {trade_reduction} 筆  |  "
                     f"勝率: {baseline.win_rate:.1f}% → {m.win_rate:.1f}%")
    lines.append("")
    lines.append("=" * 90)

    return "\n".join(lines)


if __name__ == "__main__":
    # 1. Print analysis
    analysis = print_analysis()
    print(analysis)

    # 2. Run all strategies
    print("正在執行四策略比較回測...")
    results = run_all()

    # 3. Print comparison
    comparison = print_comparison(results)
    print(comparison)

    # 4. Save full report
    report_path = "data/strategy_comparison_report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(analysis)
        f.write("\n")
        f.write(comparison)
    print(f"完整報告已儲存至: {report_path}")

    # 5. Generate equity charts for all strategies
    try:
        from txf.reporting.visualizer import plot_backtest_result

        for r in results:
            tag = r["tag"]
            chart_path = f"data/chart_{tag}.html"
            plot_backtest_result(
                r["result"].equity_curve,
                r["result"].trade_records,
                title=f"{r['name']}",
                output_html=chart_path,
            )
            print(f"  圖表: {chart_path}")
    except ImportError:
        print("(plotly 未安裝，跳過圖表)")
