"""Genetic Algorithm Engine for Alpha Factor Generation.

Evolves trading strategy parameters (genes) to optimize performance.
Uses tournament selection, uniform crossover, and gaussian mutation.
"""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from txf.reporting.metrics import calculate_metrics, PerformanceMetrics
from txf.runner import run_backtest
from txf.strategy.examples.alpha_genetic import AlphaGenetic

# Gene definitions: (min, max, type)
GENE_SPEC: dict[str, tuple[float, float, str]] = {
    "signal_type":    (0, 4, "int"),
    "trend_period":   (20, 120, "int"),
    "fast_period":    (5, 20, "int"),
    "slow_period":    (15, 50, "int"),
    "signal_period":  (3, 15, "int"),
    "osc_period":     (5, 25, "int"),
    "sl_mult":        (1.0, 3.5, "float"),
    "tp_mult":        (2.0, 6.0, "float"),
    "use_trailing":   (0, 1, "bool"),
    "trail_mult":     (1.0, 3.0, "float"),
    "trail_trigger":  (0.5, 2.0, "float"),
    "avoid_open":     (5, 30, "int"),
    "avoid_close":    (5, 30, "int"),
    "use_adx_filter": (0, 1, "bool"),
    "adx_min":        (15, 35, "float"),
    "use_rsi_filter": (0, 1, "bool"),
    "rsi_ob":         (60, 80, "float"),
    "rsi_os":         (20, 40, "float"),
    "atr_period":     (10, 20, "int"),
}


@dataclass
class Individual:
    genes: dict[str, Any]
    fitness: float = 0.0
    metrics: PerformanceMetrics | None = None
    generation: int = 0


@dataclass
class GenerationStats:
    gen: int
    best_fitness: float
    avg_fitness: float
    worst_fitness: float
    best_return_pct: float
    avg_return_pct: float
    best_win_rate: float
    best_pf: float
    best_trades: int
    best_genes: dict[str, Any] = field(default_factory=dict)


def random_genes() -> dict[str, Any]:
    """Generate a random set of genes."""
    genes = {}
    for name, (lo, hi, dtype) in GENE_SPEC.items():
        if dtype == "int":
            genes[name] = random.randint(int(lo), int(hi))
        elif dtype == "float":
            genes[name] = round(random.uniform(lo, hi), 2)
        elif dtype == "bool":
            genes[name] = random.random() > 0.5
    # Ensure fast < slow
    if genes["fast_period"] >= genes["slow_period"]:
        genes["fast_period"], genes["slow_period"] = (
            min(genes["fast_period"], genes["slow_period"]),
            max(genes["fast_period"], genes["slow_period"]) + 1,
        )
    return genes


def crossover(p1: dict, p2: dict) -> dict:
    """Uniform crossover: each gene randomly from one parent."""
    child = {}
    for name in GENE_SPEC:
        child[name] = p1[name] if random.random() < 0.5 else p2[name]
    # Fix fast < slow
    if child["fast_period"] >= child["slow_period"]:
        child["fast_period"], child["slow_period"] = (
            min(child["fast_period"], child["slow_period"]),
            max(child["fast_period"], child["slow_period"]) + 1,
        )
    return child


def mutate(genes: dict, rate: float = 0.2) -> dict:
    """Gaussian mutation with given probability per gene."""
    g = copy.deepcopy(genes)
    for name, (lo, hi, dtype) in GENE_SPEC.items():
        if random.random() > rate:
            continue
        if dtype == "int":
            delta = random.gauss(0, max(1, (hi - lo) * 0.15))
            g[name] = max(int(lo), min(int(hi), int(g[name] + delta)))
        elif dtype == "float":
            delta = random.gauss(0, (hi - lo) * 0.15)
            g[name] = round(max(lo, min(hi, g[name] + delta)), 2)
        elif dtype == "bool":
            g[name] = not g[name]
    # Fix constraint
    if g["fast_period"] >= g["slow_period"]:
        g["fast_period"], g["slow_period"] = (
            min(g["fast_period"], g["slow_period"]),
            max(g["fast_period"], g["slow_period"]) + 1,
        )
    return g


def compute_fitness(metrics: PerformanceMetrics) -> float:
    """Multi-objective fitness function."""
    ret = metrics.total_return_pct
    pf = metrics.profit_factor or 0
    wr = metrics.win_rate
    dd = metrics.max_drawdown_pct
    sh = metrics.sharpe_ratio or 0
    trades = metrics.total_trades

    # Normalize components to ~[0, 1]
    def norm(val, lo, hi):
        return max(0, min(1, (val - lo) / (hi - lo))) if hi > lo else 0.5

    f_ret = norm(ret, -15, 15)          # Return: -15% to +15% mapped to 0-1
    f_pf = norm(pf, 0, 3)              # PF: 0 to 3
    f_sh = norm(sh, -5, 5)             # Sharpe: -5 to 5
    f_dd = 1 - norm(dd, 0, 15)         # Drawdown: lower is better
    f_wr = norm(wr, 30, 70)            # Win rate: 30-70%

    # Trade count bonus: reward 15-100 trades, penalize extremes
    if trades < 5:
        f_tc = 0.0
    elif trades < 15:
        f_tc = (trades - 5) / 10
    elif trades <= 100:
        f_tc = 1.0
    elif trades <= 200:
        f_tc = 1.0 - (trades - 100) / 200
    else:
        f_tc = 0.3

    fitness = (
        0.30 * f_ret +
        0.20 * f_pf +
        0.15 * f_sh +
        0.15 * f_dd +
        0.10 * f_wr +
        0.10 * f_tc
    )
    return round(fitness, 6)


def evaluate(genes: dict, data_path: str, capital: Decimal) -> Individual:
    """Run backtest and compute fitness for a set of genes."""
    try:
        result = run_backtest(
            strategy_cls=AlphaGenetic,
            data_path=data_path,
            symbol="TX",
            strategy_params={"genes": genes},
            initial_capital=capital,
            slippage_ticks=1,
        )
        metrics = calculate_metrics(
            result.equity_curve, result.trade_records,
            capital, result.total_commission, result.total_tax,
            result.total_bars,
        )
        fitness = compute_fitness(metrics)
        ind = Individual(genes=genes, fitness=fitness, metrics=metrics)
        return ind
    except Exception as e:
        # Strategy crashed → worst fitness
        return Individual(genes=genes, fitness=0.0)


SIGNAL_NAMES = {0: "MACD", 1: "KD", 2: "Supertrend", 3: "WaveTrend", 4: "Bollinger"}


def format_genes_short(genes: dict) -> str:
    sig = SIGNAL_NAMES.get(genes["signal_type"], "?")
    trail = "T" if genes.get("use_trailing") else "-"
    adx_f = f"ADX>{genes['adx_min']:.0f}" if genes.get("use_adx_filter") else ""
    rsi_f = f"RSI" if genes.get("use_rsi_filter") else ""
    filters = "+".join(f for f in [adx_f, rsi_f] if f) or "none"
    return (f"{sig} f={genes['fast_period']}/s={genes['slow_period']} "
            f"SL={genes['sl_mult']:.1f}x/TP={genes['tp_mult']:.1f}x "
            f"trail={trail} filt={filters}")


class GeneticAlphaEngine:
    """Main GA engine for evolving trading alphas."""

    def __init__(
        self,
        population_size: int = 10,
        generations: int = 20,
        elite_count: int = 3,
        mutation_rate: float = 0.2,
        data_path: str = "",
        initial_capital: Decimal = Decimal("1000000"),
    ):
        self.pop_size = population_size
        self.n_gen = generations
        self.n_elite = elite_count
        self.mut_rate = mutation_rate
        self.data_path = data_path
        self.capital = initial_capital
        self.history: list[GenerationStats] = []
        self.all_individuals: list[Individual] = []

    def run(self) -> list[Individual]:
        """Execute the genetic algorithm evolution."""
        # Initial population
        population = [random_genes() for _ in range(self.pop_size)]

        for gen in range(self.n_gen):
            print(f"\n{'='*70}")
            print(f"  第 {gen+1}/{self.n_gen} 代")
            print(f"{'='*70}")

            # Evaluate
            individuals: list[Individual] = []
            for i, genes in enumerate(population):
                print(f"  [{i+1}/{self.pop_size}] {format_genes_short(genes)} ...", end="", flush=True)
                ind = evaluate(genes, self.data_path, self.capital)
                ind.generation = gen
                individuals.append(ind)
                self.all_individuals.append(ind)

                if ind.metrics:
                    m = ind.metrics
                    print(f" fit={ind.fitness:.4f} ret={m.total_return_pct:+.2f}% "
                          f"WR={m.win_rate:.0f}% PF={m.profit_factor:.2f} "
                          f"trades={m.total_trades}")
                else:
                    print(f" FAILED")

            # Sort by fitness
            individuals.sort(key=lambda x: x.fitness, reverse=True)

            # Stats
            fits = [x.fitness for x in individuals]
            rets = [x.metrics.total_return_pct if x.metrics else -99 for x in individuals]
            best = individuals[0]
            bm = best.metrics

            stats = GenerationStats(
                gen=gen,
                best_fitness=fits[0],
                avg_fitness=sum(fits) / len(fits),
                worst_fitness=fits[-1],
                best_return_pct=bm.total_return_pct if bm else -99,
                avg_return_pct=sum(rets) / len(rets),
                best_win_rate=bm.win_rate if bm else 0,
                best_pf=bm.profit_factor if bm else 0,
                best_trades=bm.total_trades if bm else 0,
                best_genes=copy.deepcopy(best.genes),
            )
            self.history.append(stats)

            print(f"\n  >> 第 {gen+1} 代結果: "
                  f"最佳 fit={stats.best_fitness:.4f} "
                  f"ret={stats.best_return_pct:+.2f}% "
                  f"均 fit={stats.avg_fitness:.4f} "
                  f"均 ret={stats.avg_return_pct:+.2f}%")

            if gen == self.n_gen - 1:
                break  # Don't breed on last gen

            # Select elites
            elites = [ind.genes for ind in individuals[:self.n_elite]]

            # Generate next generation
            new_pop = list(elites)  # Keep elites
            while len(new_pop) < self.pop_size:
                p1, p2 = random.sample(elites, 2)
                child = crossover(p1, p2)
                child = mutate(child, self.mut_rate)
                new_pop.append(child)
            population = new_pop

        # Return top individuals from final generation
        individuals.sort(key=lambda x: x.fitness, reverse=True)
        return individuals
