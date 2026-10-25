"""Data scraped by the original Selenium version of this project (2017 to January 2024).

The dividend table carries record and pay dates and the dividend type, which Yahoo
does not provide, so it is used to enrich live data and as a fallback when a
symbol cannot be fetched.
"""

import csv
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from .models import Company, Dividend


def _date(text: str) -> date:
    return datetime.strptime(text, "%m/%d/%Y").date()


def read_dividends(path: Path) -> dict[str, list[Dividend]]:
    """Parse rows like `1020,8/8/2022 8/9/2022 8/15/2022 0.400 Interim`."""
    result: dict[str, list[Dividend]] = {}
    with open(path, newline="") as f:
        for code, text in csv.reader(f):
            dividends = result.setdefault(code, [])
            if text.startswith("Ex date") or text.endswith("does not pay dividends"):
                continue
            ex, record, pay, amount, *kind = text.split()
            dividends.append(
                Dividend(_date(ex), float(amount), _date(record), _date(pay), " ".join(kind) or None)
            )
    return result


def read_last_close(path: Path) -> pd.Series:
    """The archived price files hold dividend-adjusted closes, which would overstate
    historical yields, so only the most recent close (where adjustment is nil) is kept."""
    frame = pd.read_csv(path)
    last = frame.dropna(subset=["Close"]).iloc[-1]
    day = pd.Timestamp(last["Date"][:10])
    return pd.Series([float(last["Close"])], index=[day])


def load(root: Path) -> dict[str, Company]:
    companies = {
        code: Company(code, dividends=sorted(divs, key=lambda d: d.ex_date), source="archive")
        for code, divs in read_dividends(root / "dividends_2017_2024.csv").items()
    }
    for path in sorted((root / "prices").glob("*.csv")):
        company = companies.setdefault(path.stem, Company(path.stem, source="archive"))
        company.prices = read_last_close(path)
    return companies
