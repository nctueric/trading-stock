"""Constants for Taiwan futures contracts.

These values are based on TAIFEX published specifications.
Margin requirements are updated periodically by TAIFEX;
the values here serve as defaults and can be overridden in config.
"""

from decimal import Decimal

# Contract multipliers (每點價值)
TX_MULTIPLIER = Decimal("200")   # 大台 1 point = 200 TWD
MTX_MULTIPLIER = Decimal("50")   # 小台 1 point = 50 TWD

# Tick sizes (最小跳動點)
TX_TICK_SIZE = Decimal("1")
MTX_TICK_SIZE = Decimal("1")

# Margin requirements (保證金, approximate as of 2024)
TX_INITIAL_MARGIN = Decimal("184000")
TX_MAINTENANCE_MARGIN = Decimal("141000")
MTX_INITIAL_MARGIN = Decimal("46000")
MTX_MAINTENANCE_MARGIN = Decimal("35250")

# Fee structure
DEFAULT_COMMISSION_PER_CONTRACT = Decimal("60")  # 手續費 per contract per side
DEFAULT_TAX_RATE = Decimal("0.00002")  # 期交稅 = 契約金額 × 十萬分之二

# Price limits (漲跌停幅度)
TX_PRICE_LIMIT_PCT = Decimal("0.10")  # ±10%
