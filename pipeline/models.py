"""Plain data containers shared by the data sources, metrics and outputs."""

from dataclasses import dataclass, field
from datetime import date

import pandas as pd


@dataclass
class Dividend:
    ex_date: date
    amount: float
    record_date: date | None = None
    pay_date: date | None = None
    kind: str | None = None  # Interim, Final, Quarterly, Special, ...


@dataclass
class AnnualFinancials:
    year: int
    revenue: float | None
    net_income: float | None


@dataclass
class Company:
    code: str
    name: str | None = None
    currency: str = "SAR"
    # Daily closing prices, not adjusted for dividends, indexed by naive dates.
    prices: pd.Series = field(
        default_factory=lambda: pd.Series(dtype=float, index=pd.DatetimeIndex([]))
    )
    dividends: list[Dividend] = field(default_factory=list)
    financials: list[AnnualFinancials] = field(default_factory=list)
    next_ex_date: date | None = None
    next_pay_date: date | None = None
    source: str = "yahoo"  # "yahoo", or "archive" when live data was unavailable
