import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from pipeline import archive, build, charts, metrics, yahoo
from pipeline.models import AnnualFinancials, Company, Dividend

ROOT = Path(__file__).resolve().parent.parent


def prices(points: dict[str, float]) -> pd.Series:
    return pd.Series(list(points.values()), index=pd.DatetimeIndex(list(points)))


def test_read_dividends_handles_headers_and_non_payers(tmp_path):
    path = tmp_path / "d.csv"
    path.write_text(
        "1020,Ex dateRecord datePay dateAmountFrequency\n"
        "1020,8/8/2022 8/9/2022 8/15/2022 0.400 Interim\n"
        "6004,8/13/2023 8/14/2023 8/31/2023 1.000 Semi Annual\n"
        "1201,1201 does not pay dividends\n"
    )
    result = archive.read_dividends(path)
    assert result["1020"] == [
        Dividend(date(2022, 8, 8), 0.4, date(2022, 8, 9), date(2022, 8, 15), "Interim")
    ]
    assert result["6004"][0].kind == "Semi Annual"
    assert result["1201"] == []


def test_archive_loads_the_real_files():
    companies = archive.load(ROOT / "data" / "archive")
    assert len(companies) == 229
    aramco = companies["2222"]
    assert aramco.prices.to_dict() == {pd.Timestamp("2024-01-15"): pytest.approx(32.4)}
    assert aramco.dividends == sorted(aramco.dividends, key=lambda d: d.ex_date)


def test_summarize_metrics():
    company = Company(
        "9999",
        prices=prices({"2021-12-30": 50.0, "2022-12-29": 40.0, "2023-12-28": 45.0, "2024-01-15": 44.0}),
        dividends=[
            Dividend(date(2018, 4, 1), 1.0),
            Dividend(date(2019, 4, 1), 1.0),
            Dividend(date(2020, 4, 1), 1.0),
            Dividend(date(2021, 4, 1), 1.5),
            Dividend(date(2022, 4, 1), 1.5),
            Dividend(date(2023, 4, 1), 1.0),
            Dividend(date(2023, 10, 1), 1.0),
            Dividend(date(2023, 10, 1), 0.5, kind="Special"),
            Dividend(date(2024, 3, 1), 1.0),  # announced, not yet ex
        ],
        financials=[AnnualFinancials(2023, 1000.0, -50.0)],
    )
    s = metrics.summarize(company, date(2024, 1, 15))
    assert s["price"] == 44.0 and s["price_date"] == "2024-01-15"
    assert s["ttm_dps"] == 2.5  # Apr 2023 is more than a year back
    assert s["yield"] == round(2.5 / 44 * 100, 2)
    assert s["frequency"] == 2  # the special shares an ex-date with a regular dividend
    assert s["streak"] == 6 and s["first_year"] == 2018
    assert s["cagr_5y"] == round(((2.5 / 1.0) ** 0.2 - 1) * 100, 1)
    assert s["last_ex"] == "2023-10-01" and s["next_ex"] == "2024-03-01"
    by_year = {row["year"]: row for row in s["annual"]}
    assert by_year[2022]["yield"] == round(1.5 / 40 * 100, 2)
    assert by_year[2020]["yield"] is None  # no closing price that year
    assert by_year[2024]["yield"] is None  # partial year
    assert by_year[2023]["margin"] == -5.0
    assert s["dividends"][0]["ex"] == "2024-03-01"


def test_summarize_without_prices_or_dividends():
    s = metrics.summarize(Company("1111"), date(2024, 1, 15))
    assert s["price"] is None and s["yield"] is None and s["streak"] == 0
    assert s["annual"] == [] and s["prices"] == []


def test_merge_archive_enriches_matching_dividends_only():
    live = Company("1", dividends=[Dividend(date(2023, 5, 2), 0.9), Dividend(date(2023, 11, 1), 1.0)])
    archived = Company("1", dividends=[
        Dividend(date(2023, 5, 1), 1.0, date(2023, 5, 3), date(2023, 5, 20), "Final"),
        Dividend(date(2020, 1, 1), 5.0),
    ])
    merged = metrics.merge_archive(live, archived)
    assert merged.dividends[0] == Dividend(date(2023, 5, 2), 0.9, date(2023, 5, 3), date(2023, 5, 20), "Final")
    assert merged.dividends[1] == Dividend(date(2023, 11, 1), 1.0)
    assert len(merged.dividends) == 2
    assert metrics.merge_archive(Company("1"), archived).dividends == archived.dividends


def test_from_yahoo_shapes():
    index = pd.DatetimeIndex(["2023-12-27", "2023-12-28"], tz="Asia/Riyadh")
    history = pd.DataFrame(
        {"Close": [10.0, 10.5], "Dividends": [0.0, 0.25], "Stock Splits": [0.0, 0.0]}, index=index
    )
    income = pd.DataFrame(
        {pd.Timestamp("2023-12-31"): [200.0, 20.0], pd.Timestamp("2022-12-31"): [180.0, float("nan")]},
        index=["Total Revenue", "Net Income"],
    )
    calendar = {"Ex-Dividend Date": date(2024, 3, 3), "Dividend Date": pd.Timestamp("2024-03-20")}
    company = yahoo.from_yahoo("1234", "Example Co", history, income, calendar)
    assert company.prices.index[0] == pd.Timestamp("2023-12-27")
    assert company.dividends == [Dividend(date(2023, 12, 28), 0.25)]
    assert company.financials == [AnnualFinancials(2022, 180.0, None), AnnualFinancials(2023, 200.0, 20.0)]
    assert company.next_ex_date == date(2024, 3, 3) and company.next_pay_date == date(2024, 3, 20)


def test_charts_render(tmp_path):
    summary = {
        "code": "1234", "name": "Example Co",
        "annual": [
            {"year": 2021, "dps": 1.0, "yield": 3.1, "revenue": 5e9, "net_income": 4e8, "margin": 8.0},
            {"year": 2022, "dps": 1.2, "yield": 2.9, "revenue": 6e9, "net_income": -2e8, "margin": -3.33},
            {"year": 2023, "dps": 1.4, "yield": None, "revenue": 7e9, "net_income": 9e8, "margin": 12.86},
        ],
    }
    assert charts.dividends_chart(summary, tmp_path / "d.png", "test")
    assert charts.performance_chart(summary, tmp_path / "p.png", "test")
    assert (tmp_path / "d.png").stat().st_size > 10_000
    assert not charts.dividends_chart({**summary, "annual": []}, tmp_path / "x.png", "test")
    assert charts.compact(1.25e9) == "1.25B" and charts.compact(-3e6) == "-3M"


def test_offline_build(tmp_path):
    assert build.main(["--offline", "--only", "2222,1120,9999", "--out", str(tmp_path)]) == 0
    data = json.loads((tmp_path / "data.json").read_text())
    assert data["as_of"] == "2024-01-15" and data["source"] == "archive"
    assert [c["code"] for c in data["companies"]] == ["1120", "2222"]
    assert (tmp_path / "charts" / "2222" / "dividends.png").exists()
