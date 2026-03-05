"""SQLAlchemy ORM models for market data persistence."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


class BarRecord(Base):
    """Persisted OHLCV bar record."""

    __tablename__ = "bars"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False)
    datetime = Column(DateTime, nullable=False)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Integer, nullable=False)
    open_interest = Column(Integer, nullable=True)
    session = Column(String(10), nullable=False, default="DAY")
    timeframe = Column(String(10), nullable=False, default="1min")

    __table_args__ = (
        UniqueConstraint("symbol", "datetime", "timeframe", name="uq_bar"),
        Index("ix_bar_symbol_dt", "symbol", "datetime"),
    )

    def __repr__(self) -> str:
        return (
            f"<BarRecord {self.symbol} {self.datetime} "
            f"O={self.open} H={self.high} L={self.low} C={self.close}>"
        )


class TradeRecordDB(Base):
    """Persisted trade record for historical analysis."""

    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False)
    side = Column(String(4), nullable=False)
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False)
    entry_time = Column(DateTime, nullable=False)
    exit_time = Column(DateTime, nullable=False)
    pnl = Column(Float, nullable=False)
    commission = Column(Float, nullable=False)
    tax = Column(Float, nullable=False)
    bars_held = Column(Integer, nullable=False, default=0)
    strategy_name = Column(String(100), nullable=True)
    backtest_id = Column(String(50), nullable=True)

    __table_args__ = (
        Index("ix_trade_symbol", "symbol"),
        Index("ix_trade_backtest", "backtest_id"),
    )


class DailyEquityRecord(Base):
    """Daily equity snapshot for drawdown tracking."""

    __tablename__ = "daily_equity"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(DateTime, nullable=False)
    equity = Column(Float, nullable=False)
    cash = Column(Float, nullable=False)
    unrealized_pnl = Column(Float, nullable=False, default=0)
    realized_pnl = Column(Float, nullable=False, default=0)
    backtest_id = Column(String(50), nullable=True)

    __table_args__ = (
        Index("ix_equity_date", "date"),
    )


def create_db_engine(db_path: str = "txf_data.db"):
    """Create a SQLAlchemy engine for the given SQLite path."""
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    Base.metadata.create_all(engine)
    return engine


def get_session(engine) -> Session:
    """Create a new database session."""
    factory = sessionmaker(bind=engine)
    return factory()
