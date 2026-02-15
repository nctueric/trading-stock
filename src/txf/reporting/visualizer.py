"""Visualization utilities for backtest results using Plotly."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from txf.core.types import TradeRecord


def plot_backtest_result(
    equity_curve: list[Decimal],
    trade_records: Optional[list[TradeRecord]] = None,
    title: str = "Backtest Result",
    output_html: Optional[str] = None,
) -> object:
    """Plot equity curve and drawdown using Plotly.

    Args:
        equity_curve: List of equity values per bar.
        trade_records: Optional trade records for entry/exit markers.
        title: Chart title.
        output_html: If provided, save to HTML file instead of showing.

    Returns:
        Plotly Figure object.
    """
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    equity = [float(e) for e in equity_curve]
    n = len(equity)

    # Calculate drawdown series
    peak = equity[0] if equity else 0
    drawdown = []
    for e in equity:
        if e > peak:
            peak = e
        dd_pct = (peak - e) / peak * 100 if peak > 0 else 0
        drawdown.append(-dd_pct)

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        row_heights=[0.7, 0.3],
        subplot_titles=["Equity Curve", "Drawdown (%)"],
    )

    # Equity curve
    fig.add_trace(
        go.Scatter(
            x=list(range(n)),
            y=equity,
            mode="lines",
            name="Equity",
            line=dict(color="#2196F3", width=1.5),
        ),
        row=1,
        col=1,
    )

    # Trade markers
    if trade_records:
        win_x = []
        win_y = []
        loss_x = []
        loss_y = []
        for _i, t in enumerate(trade_records):
            # Approximate bar index from bars_held
            idx = min(t.bars_held, n - 1) if t.bars_held > 0 else 0
            if float(t.pnl) > 0:
                win_x.append(idx)
                win_y.append(equity[idx] if idx < n else equity[-1])
            else:
                loss_x.append(idx)
                loss_y.append(equity[idx] if idx < n else equity[-1])

        if win_x:
            fig.add_trace(
                go.Scatter(
                    x=win_x,
                    y=win_y,
                    mode="markers",
                    name="Win",
                    marker=dict(color="green", size=6, symbol="triangle-up"),
                ),
                row=1,
                col=1,
            )
        if loss_x:
            fig.add_trace(
                go.Scatter(
                    x=loss_x,
                    y=loss_y,
                    mode="markers",
                    name="Loss",
                    marker=dict(color="red", size=6, symbol="triangle-down"),
                ),
                row=1,
                col=1,
            )

    # Drawdown
    fig.add_trace(
        go.Scatter(
            x=list(range(n)),
            y=drawdown,
            mode="lines",
            name="Drawdown",
            fill="tozeroy",
            line=dict(color="#F44336", width=1),
            fillcolor="rgba(244, 67, 54, 0.3)",
        ),
        row=2,
        col=1,
    )

    fig.update_layout(
        title=title,
        height=600,
        showlegend=True,
        template="plotly_white",
    )
    fig.update_xaxes(title_text="Bar Index", row=2, col=1)
    fig.update_yaxes(title_text="Equity (TWD)", row=1, col=1)
    fig.update_yaxes(title_text="Drawdown (%)", row=2, col=1)

    if output_html:
        fig.write_html(output_html)
    else:
        fig.show()

    return fig
