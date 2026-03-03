"""基因演算法 Alpha 因子自動進化系統.

自動產生交易因子 (Alpha)，經由基因演算法迭代進化：
- 20 代演化
- 每代 10 個策略
- 前 3 名作為種子產生下一代
- 完整統計分析圖表
"""

import csv
import os
import random
import sys
from datetime import datetime, timedelta, date, time
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np

from txf.strategy.genetic import (
    GeneticAlphaEngine, SIGNAL_NAMES, format_genes_short,
    Individual, GenerationStats, evaluate,
)
from txf.runner import run_backtest
from txf.reporting.metrics import calculate_metrics


INITIAL = Decimal("1000000")


# ──────────────────────────────────────────────────────────────
#  Data generation (reuse from previous scripts)
# ──────────────────────────────────────────────────────────────

def generate_data(output_path: str, months: int = 6) -> tuple[list[dict], list[date]]:
    """Generate TX 1-min bar data for GA training."""
    random.seed(2025)
    start_date = date(2025, 3, 3)
    end_date = date(2025, 3, 3) + timedelta(days=months * 31)

    tw_holidays = {
        date(2025, 4, 3), date(2025, 4, 4), date(2025, 5, 1),
        date(2025, 5, 30), date(2025, 5, 31), date(2025, 9, 29),
        date(2025, 10, 10),
    }

    trading_days: list[date] = []
    current = start_date
    while current <= end_date:
        if current.weekday() < 5 and current not in tw_holidays:
            trading_days.append(current)
        current += timedelta(days=1)

    def get_regime(td):
        month = td.month
        if month <= 4:   return "bull"
        elif month <= 6: return "range"
        elif month <= 8: return "bear"
        else:            return "recovery"

    regime_params = {
        "bull":     {"drift": 0.00015, "vol": 3.0, "gap_vol": 25},
        "bear":     {"drift": -0.00012, "vol": 3.5, "gap_vol": 35},
        "range":    {"drift": 0.0, "vol": 2.5, "gap_vol": 15},
        "recovery": {"drift": 0.00008, "vol": 3.2, "gap_vol": 20},
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
            vol_base = 180
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


# ──────────────────────────────────────────────────────────────
#  Chart generation
# ──────────────────────────────────────────────────────────────

def generate_charts(engine: GeneticAlphaEngine, top_individuals: list[Individual], output_dir: str):
    """Generate comprehensive analysis charts."""
    history = engine.history

    plt.rcParams["font.size"] = 10
    plt.rcParams["figure.facecolor"] = "white"

    # ── Chart 1: Fitness Evolution ──
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle("Genetic Alpha Evolution - 20 Generations x 10 Strategies", fontsize=16, fontweight="bold")

    gens = [s.gen + 1 for s in history]
    best_fit = [s.best_fitness for s in history]
    avg_fit = [s.avg_fitness for s in history]
    worst_fit = [s.worst_fitness for s in history]

    ax = axes[0, 0]
    ax.plot(gens, best_fit, "b-o", label="Best", linewidth=2, markersize=5)
    ax.plot(gens, avg_fit, "g--s", label="Average", linewidth=1.5, markersize=4)
    ax.plot(gens, worst_fit, "r:^", label="Worst", linewidth=1, markersize=3)
    ax.fill_between(gens, worst_fit, best_fit, alpha=0.1, color="blue")
    ax.set_xlabel("Generation")
    ax.set_ylabel("Fitness Score")
    ax.set_title("Fitness Evolution")
    ax.legend()
    ax.grid(True, alpha=0.3)

    # ── Chart 2: Return Evolution ──
    best_ret = [s.best_return_pct for s in history]
    avg_ret = [s.avg_return_pct for s in history]

    ax = axes[0, 1]
    ax.plot(gens, best_ret, "b-o", label="Best Return %", linewidth=2, markersize=5)
    ax.plot(gens, avg_ret, "g--s", label="Avg Return %", linewidth=1.5, markersize=4)
    ax.axhline(y=0, color="black", linewidth=0.5, linestyle="-")
    ax.fill_between(gens, 0, best_ret, where=[r > 0 for r in best_ret], alpha=0.2, color="green")
    ax.fill_between(gens, 0, best_ret, where=[r <= 0 for r in best_ret], alpha=0.2, color="red")
    ax.set_xlabel("Generation")
    ax.set_ylabel("Return %")
    ax.set_title("Return Evolution")
    ax.legend()
    ax.grid(True, alpha=0.3)

    # ── Chart 3: Signal Type Distribution ──
    ax = axes[1, 0]
    sig_by_gen = {}
    for ind in engine.all_individuals:
        g = ind.generation
        s = ind.genes["signal_type"]
        sig_by_gen.setdefault(g, []).append(s)

    sig_counts = {i: [] for i in range(5)}
    for g in range(engine.n_gen):
        sigs = sig_by_gen.get(g, [])
        for i in range(5):
            sig_counts[i].append(sigs.count(i))

    bottom = np.zeros(engine.n_gen)
    colors = ["#2196F3", "#FF9800", "#4CAF50", "#9C27B0", "#F44336"]
    for i in range(5):
        ax.bar(gens, sig_counts[i], bottom=bottom, color=colors[i],
               label=SIGNAL_NAMES[i], alpha=0.8)
        bottom += np.array(sig_counts[i])
    ax.set_xlabel("Generation")
    ax.set_ylabel("Count")
    ax.set_title("Signal Type Distribution per Generation")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3, axis="y")

    # ── Chart 4: Top 5 Final Strategies Comparison ──
    ax = axes[1, 1]
    top5 = top_individuals[:min(5, len(top_individuals))]
    names = [f"#{i+1}\n{SIGNAL_NAMES.get(t.genes['signal_type'], '?')}" for i, t in enumerate(top5)]
    returns = [t.metrics.total_return_pct if t.metrics else 0 for t in top5]
    bar_colors = ["#4CAF50" if r > 0 else "#F44336" for r in returns]
    bars = ax.bar(names, returns, color=bar_colors, alpha=0.8, edgecolor="black", linewidth=0.5)
    for bar, ret in zip(bars, returns):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                f"{ret:+.2f}%", ha="center", va="bottom" if ret >= 0 else "top", fontsize=9)
    ax.axhline(y=0, color="black", linewidth=0.5)
    ax.set_ylabel("Return %")
    ax.set_title("Top 5 Final Strategies - Return")
    ax.grid(True, alpha=0.3, axis="y")

    plt.tight_layout()
    path1 = os.path.join(output_dir, "ga_evolution.png")
    fig.savefig(path1, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Chart 1: {path1}")

    # ── Chart 5: Detailed Top Strategy Metrics ──
    fig2, axes2 = plt.subplots(1, 3, figsize=(18, 6))
    fig2.suptitle("Top 5 Strategies - Detailed Metrics", fontsize=14, fontweight="bold")

    # Win Rate & PF
    ax = axes2[0]
    x = np.arange(len(top5))
    width = 0.35
    wr = [t.metrics.win_rate if t.metrics else 0 for t in top5]
    pf = [min(t.metrics.profit_factor, 5) if t.metrics and t.metrics.profit_factor else 0 for t in top5]
    ax.bar(x - width/2, wr, width, label="Win Rate %", color="#2196F3", alpha=0.8)
    ax2 = ax.twinx()
    ax2.bar(x + width/2, pf, width, label="Profit Factor", color="#FF9800", alpha=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels([f"#{i+1}" for i in range(len(top5))])
    ax.set_ylabel("Win Rate %")
    ax2.set_ylabel("Profit Factor")
    ax.legend(loc="upper left")
    ax2.legend(loc="upper right")
    ax.set_title("Win Rate & Profit Factor")
    ax.grid(True, alpha=0.3, axis="y")

    # Trades & Costs
    ax = axes2[1]
    trades = [t.metrics.total_trades if t.metrics else 0 for t in top5]
    costs = [float(t.metrics.total_commission + t.metrics.total_tax) if t.metrics else 0 for t in top5]
    ax.bar(x - width/2, trades, width, label="Trades", color="#4CAF50", alpha=0.8)
    ax3 = ax.twinx()
    ax3.bar(x + width/2, costs, width, label="Cost (NT$)", color="#F44336", alpha=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels([f"#{i+1}" for i in range(len(top5))])
    ax.set_ylabel("Trade Count")
    ax3.set_ylabel("Transaction Cost (NT$)")
    ax.legend(loc="upper left")
    ax3.legend(loc="upper right")
    ax.set_title("Trades & Transaction Costs")
    ax.grid(True, alpha=0.3, axis="y")

    # Risk metrics
    ax = axes2[2]
    dd = [t.metrics.max_drawdown_pct if t.metrics else 0 for t in top5]
    sharpe = [t.metrics.sharpe_ratio if t.metrics and t.metrics.sharpe_ratio else 0 for t in top5]
    ax.bar(x - width/2, dd, width, label="Max DD %", color="#F44336", alpha=0.8)
    ax4 = ax.twinx()
    ax4.bar(x + width/2, sharpe, width, label="Sharpe", color="#9C27B0", alpha=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels([f"#{i+1}" for i in range(len(top5))])
    ax.set_ylabel("Max Drawdown %")
    ax4.set_ylabel("Sharpe Ratio")
    ax.legend(loc="upper left")
    ax4.legend(loc="upper right")
    ax.set_title("Risk Metrics")
    ax.grid(True, alpha=0.3, axis="y")

    plt.tight_layout()
    path2 = os.path.join(output_dir, "ga_top5_metrics.png")
    fig2.savefig(path2, dpi=150, bbox_inches="tight")
    plt.close(fig2)
    print(f"  Chart 2: {path2}")

    # ── Chart 6: Gene Parameter Heatmap ──
    fig3, ax = plt.subplots(figsize=(14, 8))
    param_names = ["signal_type", "trend_period", "fast_period", "slow_period",
                   "osc_period", "sl_mult", "tp_mult", "use_trailing",
                   "use_adx_filter", "adx_min", "use_rsi_filter", "atr_period"]

    best_genes_per_gen = [s.best_genes for s in history]
    matrix = []
    for genes in best_genes_per_gen:
        row = []
        for p in param_names:
            v = genes.get(p, 0)
            if isinstance(v, bool):
                v = 1.0 if v else 0.0
            row.append(float(v))
        matrix.append(row)
    matrix = np.array(matrix)
    # Normalize each column
    for j in range(matrix.shape[1]):
        col = matrix[:, j]
        mn, mx = col.min(), col.max()
        if mx > mn:
            matrix[:, j] = (col - mn) / (mx - mn)
        else:
            matrix[:, j] = 0.5

    im = ax.imshow(matrix.T, aspect="auto", cmap="YlOrRd", interpolation="nearest")
    ax.set_xticks(range(len(history)))
    ax.set_xticklabels([str(s.gen + 1) for s in history], fontsize=8)
    ax.set_yticks(range(len(param_names)))
    ax.set_yticklabels(param_names, fontsize=9)
    ax.set_xlabel("Generation")
    ax.set_title("Best Gene Parameters Evolution (Normalized Heatmap)", fontsize=13)
    plt.colorbar(im, ax=ax, label="Normalized Value")

    plt.tight_layout()
    path3 = os.path.join(output_dir, "ga_gene_heatmap.png")
    fig3.savefig(path3, dpi=150, bbox_inches="tight")
    plt.close(fig3)
    print(f"  Chart 3: {path3}")

    # ── Chart 7: Fitness scatter of all individuals ──
    fig4, ax = plt.subplots(figsize=(12, 6))
    all_gens = [ind.generation + 1 for ind in engine.all_individuals]
    all_fits = [ind.fitness for ind in engine.all_individuals]
    all_rets = [ind.metrics.total_return_pct if ind.metrics else -15 for ind in engine.all_individuals]

    scatter = ax.scatter(all_gens, all_rets, c=all_fits, cmap="RdYlGn",
                         s=50, alpha=0.7, edgecolors="black", linewidth=0.3)
    plt.colorbar(scatter, ax=ax, label="Fitness Score")
    ax.axhline(y=0, color="black", linewidth=0.5, linestyle="--")

    # Connect best per generation
    best_gen_rets = [s.best_return_pct for s in history]
    ax.plot(gens, best_gen_rets, "r-o", linewidth=2, markersize=6, label="Best per Gen", zorder=5)

    ax.set_xlabel("Generation")
    ax.set_ylabel("Return %")
    ax.set_title("All Individuals - Return vs Generation (color = fitness)")
    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    path4 = os.path.join(output_dir, "ga_scatter.png")
    fig4.savefig(path4, dpi=150, bbox_inches="tight")
    plt.close(fig4)
    print(f"  Chart 4: {path4}")


# ──────────────────────────────────────────────────────────────
#  Report
# ──────────────────────────────────────────────────────────────

def build_report(engine: GeneticAlphaEngine, top: list[Individual], trading_days, all_bars) -> str:
    L = []
    L.append("")
    L.append("=" * 96)
    L.append("  基因演算法 Alpha 因子自動進化系統 — 完整報告")
    L.append(f"  訓練資料: {trading_days[0]} ~ {trading_days[-1]} "
             f"({len(trading_days)} 交易日, {len(all_bars):,} 根 1-min K)")
    L.append(f"  演化參數: {engine.n_gen} 代 × {engine.pop_size} 策略/代 = "
             f"{engine.n_gen * engine.pop_size} 次回測")
    L.append(f"  菁英保留: 前 {engine.n_elite} 名 | 突變率: {engine.mut_rate:.0%}")
    L.append("=" * 96)
    L.append("")

    # Evolution summary
    L.append("  [ 演化過程摘要 ]")
    L.append("  ┌──────┬──────────┬──────────┬──────────┬──────────┬──────┬──────┐")
    L.append("  │ 世代 │ 最佳fit  │ 均fit    │ 最佳ret  │ 均ret    │ 最佳WR│交易數│")
    L.append("  ├──────┼──────────┼──────────┼──────────┼──────────┼──────┼──────┤")
    for s in engine.history:
        L.append(f"  │  {s.gen+1:>3} │ {s.best_fitness:>8.4f} │ {s.avg_fitness:>8.4f} │"
                 f" {s.best_return_pct:>+7.2f}% │ {s.avg_return_pct:>+7.2f}% │"
                 f" {s.best_win_rate:>4.0f}% │ {s.best_trades:>4} │")
    L.append("  └──────┴──────────┴──────────┴──────────┴──────────┴──────┴──────┘")
    L.append("")

    # Top 5
    L.append("=" * 96)
    L.append("  [ 最終 Top 5 策略 ]")
    L.append("=" * 96)
    L.append("")

    for i, ind in enumerate(top[:5]):
        m = ind.metrics
        g = ind.genes
        if not m:
            continue
        sig = SIGNAL_NAMES.get(g["signal_type"], "?")
        L.append(f"  ── 第 {i+1} 名 (fitness={ind.fitness:.4f}) ──")
        L.append(f"  訊號類型: {sig} | EMA趨勢={g['trend_period']} | "
                 f"快={g['fast_period']}/慢={g['slow_period']} | 振盪={g['osc_period']}")
        L.append(f"  SL={g['sl_mult']:.1f}x ATR | TP={g['tp_mult']:.1f}x ATR | "
                 f"追蹤停損={'On' if g.get('use_trailing') else 'Off'}"
                 + (f" ({g['trail_mult']:.1f}x)" if g.get("use_trailing") else ""))
        filters = []
        if g.get("use_adx_filter"):
            filters.append(f"ADX>{g['adx_min']:.0f}")
        if g.get("use_rsi_filter"):
            filters.append(f"RSI({g['rsi_os']:.0f}-{g['rsi_ob']:.0f})")
        L.append(f"  過濾器: {', '.join(filters) if filters else '無'} | "
                 f"避開開盤前{g['avoid_open']}分/收盤前{g['avoid_close']}分")
        L.append(f"  報酬: {m.total_return_pct:+.2f}% (NT${float(m.total_return):+,.0f}) | "
                 f"交易: {m.total_trades}筆 | 勝率: {m.win_rate:.1f}%")
        pf = m.profit_factor if m.profit_factor else 0
        sh = f"{m.sharpe_ratio:.2f}" if m.sharpe_ratio else "N/A"
        L.append(f"  PF: {pf:.2f} | Sharpe: {sh} | "
                 f"最大回撤: {m.max_drawdown_pct:.2f}% | "
                 f"成本: NT${float(m.total_commission + m.total_tax):,.0f}")
        L.append("")

    # Overall stats
    all_rets = [ind.metrics.total_return_pct for ind in engine.all_individuals if ind.metrics]
    profitable = sum(1 for r in all_rets if r > 0)
    L.append("=" * 96)
    L.append("  [ 整體統計 ]")
    L.append("=" * 96)
    L.append(f"  總共測試: {len(all_rets)} 個策略組合")
    L.append(f"  獲利策略: {profitable} ({profitable/len(all_rets)*100:.1f}%)")
    L.append(f"  虧損策略: {len(all_rets) - profitable} ({(len(all_rets)-profitable)/len(all_rets)*100:.1f}%)")
    L.append(f"  最佳報酬: {max(all_rets):+.2f}%")
    L.append(f"  最差報酬: {min(all_rets):+.2f}%")
    L.append(f"  平均報酬: {sum(all_rets)/len(all_rets):+.2f}%")

    # Signal type analysis
    sig_rets: dict[int, list[float]] = {}
    for ind in engine.all_individuals:
        if ind.metrics:
            s = ind.genes["signal_type"]
            sig_rets.setdefault(s, []).append(ind.metrics.total_return_pct)
    L.append("")
    L.append("  [ 各訊號類型平均表現 ]")
    for s in sorted(sig_rets.keys()):
        rets = sig_rets[s]
        avg = sum(rets) / len(rets)
        best = max(rets)
        L.append(f"  {SIGNAL_NAMES[s]:>12}: 平均 {avg:+.2f}% | 最佳 {best:+.2f}% | 測試 {len(rets)} 次")

    L.append("")
    L.append("=" * 96)
    return "\n".join(L)


# ──────────────────────────────────────────────────────────────
#  Main
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)

    # 1. Prepare data (6 months for reasonable speed)
    csv_path = "data/tx_1min_6month.csv"
    if not os.path.exists(csv_path):
        print("正在產生 6 個月 TX 1-min K 線資料...")
        all_bars, trading_days = generate_data(csv_path, months=6)
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

    # 2. Run GA
    print("\n" + "=" * 70)
    print("  啟動基因演算法 Alpha 因子進化系統")
    print(f"  20 代 × 10 策略/代 = 200 次回測")
    print("=" * 70)

    random.seed(42)  # Reproducible GA

    engine = GeneticAlphaEngine(
        population_size=10,
        generations=20,
        elite_count=3,
        mutation_rate=0.2,
        data_path=csv_path,
        initial_capital=INITIAL,
    )

    top_individuals = engine.run()

    # 3. Generate report
    report = build_report(engine, top_individuals, trading_days, all_bars)
    print(report)

    report_path = "data/genetic_alpha_report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n報告已儲存: {report_path}")

    # 4. Generate charts
    print("\n正在產生統計分析圖表...")
    generate_charts(engine, top_individuals, "data")

    print("\n" + "=" * 70)
    print("  基因演算法 Alpha 因子進化完成!")
    print("=" * 70)
