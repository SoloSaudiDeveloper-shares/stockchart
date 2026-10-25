# Tawzi: Saudi dividend tracker

Dividend history, yields, upcoming payouts and projected portfolio income for companies
listed on the Saudi Exchange. It replaces the original Selenium script, which took
screenshots of TradingView pages, with a data pipeline and a website that installs on a
phone like an app.

## How it works

```
data/symbols.csv ──► pipeline (Yahoo Finance) ──► site/data.json ──► site/ (web app)
data/archive/    ──┘   metrics + PNG charts   ──► site/charts/<code>/*.png
```

- **`pipeline/`** fetches prices, dividends and annual financials for each symbol
  (`2222` becomes `2222.SR` on Yahoo), computes yield, payment streak, payout frequency
  and 5-year dividend growth, and draws two charts per company: dividends per share and
  revenue/net income. A full run over about 240 symbols takes a few minutes, with no browser.
- **`data/archive/`** holds the dividend table and prices the old scraper collected
  (2017 to January 2024). It adds record and pay dates and dividend types, which Yahoo
  does not have, and stands in for any symbol Yahoo fails to return.
- **`site/`** is a static web app: upcoming dividends, a screener, a page per company and
  a portfolio income planner. It works offline once installed (manifest and service worker).
- **`.github/workflows/update.yml`** runs the pipeline after market close, Sunday to
  Thursday, and publishes `site/` to GitHub Pages.

## Run it locally

```sh
pip install -r requirements.txt pytest
python -m pytest -q
python -m pipeline.build              # live data (needs access to Yahoo Finance)
python -m pipeline.build --offline    # archived data only
python -m http.server --directory site
```

Then open http://localhost:8000. Add symbols by appending their codes to
`data/symbols.csv`; names are filled in on the next live run.

## Turn on the website

In the repository settings, open **Pages** and set **Source** to **GitHub Actions**. Then
run the workflow from the **Actions** tab (or wait for the schedule).

## Data caveats

Yahoo Finance is fine for a prototype, but its terms do not allow redistributing the
data, and a paid product needs a licensed market-data feed. `pipeline/yahoo.py` is the
only module that talks to the source, so a licensed provider can replace it behind the
same `fetch(code, name)` function. Nothing here is investment advice.
