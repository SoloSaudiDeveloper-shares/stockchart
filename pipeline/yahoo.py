"""Live data from Yahoo Finance through yfinance. Tadawul tickers use the `.SR` suffix.

Yahoo's data is fine for a prototype but its terms do not allow redistribution, so a
paid product needs a licensed feed behind the same `fetch` signature.
"""

import logging
import time
from datetime import date, datetime

import pandas as pd
import yfinance as yf

from .models import AnnualFinancials, Company, Dividend

log = logging.getLogger(__name__)


class NoData(LookupError):
    """Yahoo has no history for the ticker (delisted or wrong code); not worth retrying."""


def fetch(code: str, name: str | None = None, retries: int = 3) -> Company:
    for attempt in range(1, retries + 1):
        try:
            return _fetch_once(code, name)
        except NoData:
            raise
        except Exception as e:
            if attempt == retries:
                raise
            wait = 2**attempt
            log.warning("%s: %s; retrying in %ss", code, e, wait)
            time.sleep(wait)
    raise AssertionError("unreachable")


def _fetch_once(code: str, name: str | None) -> Company:
    ticker = yf.Ticker(f"{code}.SR")
    # auto_adjust=False keeps real closes; adjusted ones would distort historical yields.
    history = ticker.history(period="max", auto_adjust=False, actions=True)
    if history.empty:
        raise NoData(f"no price history for {code}.SR")
    income = _optional(code, "income statement", lambda: ticker.income_stmt)
    calendar = _optional(code, "calendar", lambda: ticker.calendar)
    if not name:
        info = _optional(code, "info", lambda: ticker.info) or {}
        name = info.get("longName") or info.get("shortName")
    return from_yahoo(code, name, history, income, calendar)


def _optional(code, what, getter):
    try:
        return getter()
    except Exception as e:
        log.info("%s: no %s (%s)", code, what, e)
        return None


def from_yahoo(code, name, history: pd.DataFrame, income: pd.DataFrame | None, calendar) -> Company:
    days = history.index.tz_localize(None) if history.index.tz is not None else history.index
    days = days.normalize()
    prices = pd.Series(history["Close"].to_numpy(), index=days).dropna()
    paid = history["Dividends"].to_numpy() > 0
    dividends = [
        Dividend(day.date(), round(float(amount), 6))
        for day, amount in zip(days[paid], history["Dividends"].to_numpy()[paid])
    ]
    calendar = calendar if isinstance(calendar, dict) else {}
    return Company(
        code,
        name=name,
        prices=prices,
        dividends=dividends,
        financials=_financials(income),
        next_ex_date=_as_date(calendar.get("Ex-Dividend Date")),
        next_pay_date=_as_date(calendar.get("Dividend Date")),
    )


def _financials(income: pd.DataFrame | None) -> list[AnnualFinancials]:
    if income is None or income.empty:
        return []
    by_year: dict[int, AnnualFinancials] = {}
    for column in sorted(income.columns):
        revenue = _cell(income, "Total Revenue", column)
        net_income = _cell(income, "Net Income", column)
        if revenue is not None or net_income is not None:
            by_year[column.year] = AnnualFinancials(column.year, revenue, net_income)
    return [by_year[year] for year in sorted(by_year)]


def _cell(frame: pd.DataFrame, row: str, column) -> float | None:
    if row not in frame.index:
        return None
    value = frame.at[row, column]
    return None if pd.isna(value) else float(value)


def _as_date(value) -> date | None:
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, datetime):  # includes pd.Timestamp
        return value.date()
    return value if isinstance(value, date) else None
