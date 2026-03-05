"""Tests for data normalizer including continuous contract builder."""

from datetime import datetime
from decimal import Decimal

from txf.core.types import Bar, SessionType
from txf.data.normalizer import build_continuous_contract, _parse_roc_date


def _bar(dt: datetime, close: int, symbol: str = "TX") -> Bar:
    return Bar(
        symbol=symbol,
        datetime=dt,
        open=Decimal(str(close)),
        high=Decimal(str(close + 50)),
        low=Decimal(str(close - 50)),
        close=Decimal(str(close)),
        volume=1000,
        session=SessionType.DAY,
    )


def test_parse_roc_date():
    dt = _parse_roc_date("113/01/15")
    assert dt == datetime(2024, 1, 15)


def test_parse_roc_date_invalid():
    assert _parse_roc_date("abc") is None
    assert _parse_roc_date("") is None


def test_continuous_unadjusted():
    bars_by_month = {
        "202401": [
            _bar(datetime(2024, 1, 2), 20000),
            _bar(datetime(2024, 1, 3), 20100),
        ],
        "202402": [
            _bar(datetime(2024, 1, 3), 20120),  # overlap date
            _bar(datetime(2024, 2, 1), 20200),
        ],
    }
    result = build_continuous_contract(bars_by_month, method="unadjusted")
    # Deduplicated by datetime, keeps first occurrence
    dates = [b.datetime for b in result]
    assert len(set(dates)) == len(dates)  # no duplicates
    assert len(result) == 3  # Jan 2, Jan 3 (first), Feb 1


def test_continuous_back_adjust():
    # Month 1: closes at 20000, 20100 on the overlap date
    # Month 2: closes at 20120 on the overlap date, then 20200
    # Gap = 20120 - 20100 = 20 points
    # So month 1 bars should be adjusted down by 20
    bars_by_month = {
        "202401": [
            _bar(datetime(2024, 1, 2), 20000),
            _bar(datetime(2024, 1, 3), 20100),  # roll date (overlap)
        ],
        "202402": [
            _bar(datetime(2024, 1, 3), 20120),  # overlap
            _bar(datetime(2024, 2, 1), 20200),
        ],
    }
    result = build_continuous_contract(bars_by_month, method="back_adjust")
    # Month 1 bars adjusted by -20
    jan2 = [b for b in result if b.datetime == datetime(2024, 1, 2)][0]
    assert jan2.close == Decimal("19980")  # 20000 - 20

    jan3 = [b for b in result if b.datetime == datetime(2024, 1, 3)][0]
    assert jan3.close == Decimal("20080")  # 20100 - 20


def test_continuous_empty():
    assert build_continuous_contract({}) == []
