"""Trade log: persist and export trade records."""

from __future__ import annotations

import csv
from pathlib import Path

from txf.core.types import TradeRecord


class TradeLogger:
    """Collects and exports trade records."""

    HEADERS = [
        "symbol",
        "side",
        "entry_price",
        "exit_price",
        "quantity",
        "entry_time",
        "exit_time",
        "pnl",
        "commission",
        "tax",
        "bars_held",
    ]

    def __init__(self) -> None:
        self._records: list[TradeRecord] = []

    def add(self, record: TradeRecord) -> None:
        self._records.append(record)

    def add_all(self, records: list[TradeRecord]) -> None:
        self._records.extend(records)

    @property
    def records(self) -> list[TradeRecord]:
        return list(self._records)

    def to_csv(self, file_path: str | Path) -> None:
        """Export trade records to CSV."""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(self.HEADERS)
            for r in self._records:
                writer.writerow(
                    [
                        r.symbol,
                        r.side.value,
                        str(r.entry_price),
                        str(r.exit_price),
                        r.quantity,
                        r.entry_time.isoformat() if r.entry_time else "",
                        r.exit_time.isoformat() if r.exit_time else "",
                        str(r.pnl),
                        str(r.commission),
                        str(r.tax),
                        r.bars_held,
                    ]
                )

    def summary(self) -> str:
        """Return a brief text summary."""
        if not self._records:
            return "No trades recorded."
        total_pnl = sum(r.pnl for r in self._records)
        wins = sum(1 for r in self._records if r.pnl > 0)
        return (
            f"Trades: {len(self._records)} | "
            f"Wins: {wins} | "
            f"Losses: {len(self._records) - wins} | "
            f"Total PnL: {total_pnl:,.0f} TWD"
        )
