"""Dividend and financial metrics, and the JSON shape the website reads."""

from dataclasses import replace
from datetime import date, timedelta

import pandas as pd

from .models import Company

MATCH_WINDOW = timedelta(days=3)


def merge_archive(live: Company, archived: Company | None) -> Company:
    """Copy record/pay dates and dividend type from the archive onto matching live dividends.

    Amounts stay Yahoo's because they are adjusted for bonus shares and the archive's are
    not. For the same reason, archive rows with no live match are only used when Yahoo
    has no dividends at all for the symbol.
    """
    if archived is None or not archived.dividends:
        return live
    if not live.dividends:
        return replace(live, dividends=archived.dividends)
    dividends = []
    for dividend in live.dividends:
        match = next(
            (a for a in archived.dividends if abs(a.ex_date - dividend.ex_date) <= MATCH_WINDOW), None
        )
        if match:
            dividend = replace(
                dividend, record_date=match.record_date, pay_date=match.pay_date, kind=match.kind
            )
        dividends.append(dividend)
    return replace(live, dividends=dividends)


def dividends_by_year(company: Company) -> dict[int, float]:
    totals: dict[int, float] = {}
    for d in company.dividends:
        totals[d.ex_date.year] = totals.get(d.ex_date.year, 0.0) + d.amount
    return totals


def year_end_closes(company: Company) -> dict[int, float]:
    if company.prices.empty:
        return {}
    last = company.prices.groupby(company.prices.index.year).last()
    return {int(year): float(close) for year, close in last.items()}


def summarize(company: Company, as_of: date) -> dict:
    by_year = dividends_by_year(company)
    closes = year_end_closes(company)
    last_full_year = as_of.year - 1

    prices = company.prices[company.prices.index <= pd.Timestamp(as_of)]
    price = float(prices.iloc[-1]) if not prices.empty else None
    price_date = prices.index[-1].date() if not prices.empty else None

    ttm = sum(d.amount for d in company.dividends if as_of - timedelta(days=365) < d.ex_date <= as_of)
    streak = 0
    while by_year.get(last_full_year - streak, 0) > 0:
        streak += 1
    start, end = by_year.get(last_full_year - 5), by_year.get(last_full_year)
    cagr = (end / start) ** (1 / 5) - 1 if start and end else None
    # Distinct dates, so a special dividend paid alongside a regular one does not count twice.
    frequency = len({d.ex_date for d in company.dividends if d.ex_date.year == last_full_year}) or None

    financials = {f.year: f for f in company.financials}
    annual = []
    for year in sorted(set(by_year) | set(financials)):
        dps = by_year.get(year, 0.0)
        f = financials.get(year)
        margin = (
            f.net_income / f.revenue * 100 if f and f.revenue and f.net_income is not None else None
        )
        annual.append({
            "year": year,
            "dps": _round(dps, 4),
            # A year's yield needs its closing price, so the current, partial year has none.
            "yield": _round(dps / closes[year] * 100, 2) if year < as_of.year and closes.get(year) else None,
            "revenue": _round(f.revenue, 0) if f else None,
            "net_income": _round(f.net_income, 0) if f else None,
            "margin": _round(margin, 2),
        })

    upcoming = [d for d in company.dividends if d.ex_date > as_of]
    next_ex = company.next_ex_date if company.next_ex_date and company.next_ex_date > as_of else None
    if not next_ex and upcoming:
        next_ex = min(d.ex_date for d in upcoming)
    monthly = company.prices[company.prices.index > pd.Timestamp(as_of - timedelta(days=5 * 366))]
    monthly = monthly.groupby(monthly.index.to_period("M")).last()

    return {
        "code": company.code,
        "name": company.name,
        "currency": company.currency,
        "source": company.source,
        "price": _round(price, 2),
        "price_date": _iso(price_date),
        "ttm_dps": _round(ttm, 4),
        "yield": _round(ttm / price * 100, 2) if price and ttm else None,
        "frequency": frequency,
        "streak": streak,
        "first_year": min(by_year) if by_year else None,
        "cagr_5y": _round(cagr * 100, 1) if cagr is not None else None,
        "last_ex": _iso(max((d.ex_date for d in company.dividends if d.ex_date <= as_of), default=None)),
        "next_ex": _iso(next_ex),
        "next_pay": _iso(company.next_pay_date if company.next_pay_date and company.next_pay_date > as_of else None),
        "annual": annual,
        "dividends": [
            {
                "ex": _iso(d.ex_date),
                "record": _iso(d.record_date),
                "pay": _iso(d.pay_date),
                "amount": _round(d.amount, 4),
                "kind": d.kind,
            }
            for d in sorted(company.dividends, key=lambda d: d.ex_date, reverse=True)
        ],
        "prices": [[str(month), _round(close, 2)] for month, close in monthly.items()],
    }


def _round(value, digits):
    if value is None:
        return None
    return int(round(value)) if digits == 0 else round(float(value), digits)


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None
