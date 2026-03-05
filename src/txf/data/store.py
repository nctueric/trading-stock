"""DataStore: read/write market data to SQLite via SQLAlchemy."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from txf.core.types import Bar, SessionType, TradeRecord, Side
from txf.data.models import (
    BarRecord,
    DailyEquityRecord,
    TradeRecordDB,
    create_db_engine,
    get_session,
)


class DataStore:
    """Persistent storage for bars, trades, and equity snapshots.

    Uses SQLite as the backend. Handles conversion between
    domain types (Bar, TradeRecord) and ORM models.
    """

    def __init__(self, db_path: str = "txf_data.db") -> None:
        self._engine = create_db_engine(db_path)

    def _session(self) -> Session:
        return get_session(self._engine)

    # -- Bar operations --

    def save_bars(self, bars: list[Bar], timeframe: str = "1min") -> int:
        """Save bars to database. Skips duplicates. Returns count saved."""
        session = self._session()
        saved = 0
        try:
            for bar in bars:
                existing = session.execute(
                    select(BarRecord).where(
                        and_(
                            BarRecord.symbol == bar.symbol,
                            BarRecord.datetime == bar.datetime,
                            BarRecord.timeframe == timeframe,
                        )
                    )
                ).scalar_one_or_none()

                if existing is not None:
                    continue

                record = BarRecord(
                    symbol=bar.symbol,
                    datetime=bar.datetime,
                    open=float(bar.open),
                    high=float(bar.high),
                    low=float(bar.low),
                    close=float(bar.close),
                    volume=bar.volume,
                    open_interest=bar.open_interest,
                    session=bar.session.value,
                    timeframe=timeframe,
                )
                session.add(record)
                saved += 1

            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
        return saved

    def load_bars(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        timeframe: str = "1min",
    ) -> list[Bar]:
        """Load bars from database, sorted by datetime."""
        session = self._session()
        try:
            query = select(BarRecord).where(
                and_(
                    BarRecord.symbol == symbol,
                    BarRecord.timeframe == timeframe,
                )
            )
            if start_date:
                query = query.where(BarRecord.datetime >= start_date)
            if end_date:
                query = query.where(BarRecord.datetime <= end_date)
            query = query.order_by(BarRecord.datetime)

            results = session.execute(query).scalars().all()
            return [self._record_to_bar(r) for r in results]
        finally:
            session.close()

    def count_bars(self, symbol: str, timeframe: str = "1min") -> int:
        """Count bars in database for a symbol."""
        session = self._session()
        try:
            from sqlalchemy import func

            result = session.execute(
                select(func.count(BarRecord.id)).where(
                    and_(
                        BarRecord.symbol == symbol,
                        BarRecord.timeframe == timeframe,
                    )
                )
            ).scalar()
            return result or 0
        finally:
            session.close()

    def get_date_range(
        self, symbol: str, timeframe: str = "1min"
    ) -> tuple[Optional[datetime], Optional[datetime]]:
        """Get the earliest and latest bar datetime for a symbol."""
        session = self._session()
        try:
            from sqlalchemy import func

            row = session.execute(
                select(
                    func.min(BarRecord.datetime),
                    func.max(BarRecord.datetime),
                ).where(
                    and_(
                        BarRecord.symbol == symbol,
                        BarRecord.timeframe == timeframe,
                    )
                )
            ).one()
            return row[0], row[1]
        finally:
            session.close()

    # -- Trade operations --

    def save_trades(
        self,
        trades: list[TradeRecord],
        strategy_name: str = "",
        backtest_id: str = "",
    ) -> int:
        """Save trade records to database. Returns count saved."""
        session = self._session()
        try:
            for t in trades:
                record = TradeRecordDB(
                    symbol=t.symbol,
                    side=t.side.value,
                    entry_price=float(t.entry_price),
                    exit_price=float(t.exit_price),
                    quantity=t.quantity,
                    entry_time=t.entry_time,
                    exit_time=t.exit_time,
                    pnl=float(t.pnl),
                    commission=float(t.commission),
                    tax=float(t.tax),
                    bars_held=t.bars_held,
                    strategy_name=strategy_name,
                    backtest_id=backtest_id,
                )
                session.add(record)
            session.commit()
            return len(trades)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # -- Equity operations --

    def save_equity_curve(
        self,
        equity_curve: list[Decimal],
        dates: list[datetime],
        backtest_id: str = "",
    ) -> int:
        """Save equity curve snapshots."""
        session = self._session()
        try:
            for eq, dt in zip(equity_curve, dates):
                record = DailyEquityRecord(
                    date=dt,
                    equity=float(eq),
                    cash=float(eq),
                    backtest_id=backtest_id,
                )
                session.add(record)
            session.commit()
            return len(equity_curve)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # -- Helpers --

    @staticmethod
    def _record_to_bar(r: BarRecord) -> Bar:
        return Bar(
            symbol=r.symbol,
            datetime=r.datetime,
            open=Decimal(str(r.open)),
            high=Decimal(str(r.high)),
            low=Decimal(str(r.low)),
            close=Decimal(str(r.close)),
            volume=r.volume,
            open_interest=r.open_interest,
            session=SessionType(r.session) if r.session else SessionType.DAY,
        )
