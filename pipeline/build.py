"""Build the website data and charts for every symbol in data/symbols.csv.

    python -m pipeline.build              # live data from Yahoo, then charts
    python -m pipeline.build --offline    # archived data only (no network)
    python -m pipeline.build --only 2222,1120 --no-charts
"""

import argparse
import csv
import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path

from . import archive, charts, metrics
from .models import Company

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger("pipeline")


def read_symbols(path: Path) -> dict[str, str | None]:
    with open(path, newline="") as f:
        return {row["code"]: row["name"] or None for row in csv.DictReader(f)}


def write_symbols(path: Path, symbols: dict[str, str | None]) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["code", "name"])
        writer.writerows((code, symbols[code] or "") for code in sorted(symbols))


def fetch_live(symbols, archived, workers) -> tuple[list[Company], list[str]]:
    from . import yahoo  # imported here so --offline works without yfinance installed

    def one(code):
        try:
            return metrics.merge_archive(yahoo.fetch(code, symbols[code]), archived.get(code))
        except Exception as e:
            log.warning("%s: live fetch failed (%s)", code, e)
            return None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = dict(zip(symbols, pool.map(one, symbols)))
    companies, failed = [], []
    for code, company in results.items():
        if company is None:
            failed.append(code)
            company = archived.get(code)
        if company is not None:
            company.name = company.name or symbols[code]
            companies.append(company)
    return companies, failed


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--offline", action="store_true", help="use archived data only")
    parser.add_argument("--only", help="comma-separated symbol codes")
    parser.add_argument("--no-charts", action="store_true", help="skip PNG charts")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--out", type=Path, default=ROOT / "site")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    symbols_path = ROOT / "data" / "symbols.csv"
    symbols = read_symbols(symbols_path)
    if args.only:
        wanted = args.only.split(",")
        symbols = {code: symbols.get(code) for code in wanted}
    archived = archive.load(ROOT / "data" / "archive")

    if args.offline:
        companies = [archived[code] for code in symbols if code in archived]
        for company in companies:
            company.name = company.name or symbols[company.code]
        failed = []
        latest = [c.prices.index[-1] for c in companies if not c.prices.empty]
        as_of = max(latest).date() if latest else date.today()
        source_note = f"Archived data (2017 to {as_of:%b %Y}) · not investment advice"
    else:
        companies, failed = fetch_live(symbols, archived, args.workers)
        as_of = date.today()
        source_note = f"Source: Yahoo Finance · data as of {as_of:%d %b %Y} · not investment advice"
        if len(failed) > len(symbols) / 2:
            log.error("%d of %d symbols failed; not publishing", len(failed), len(symbols))
            return 1

    summaries = [metrics.summarize(c, as_of) for c in sorted(companies, key=lambda c: c.code)]
    for s in summaries:
        s["charts"] = []
        if not args.no_charts:
            folder = args.out / "charts" / s["code"]
            if charts.dividends_chart(s, folder / "dividends.png", source_note):
                s["charts"].append("dividends")
            if charts.performance_chart(s, folder / "performance.png", source_note):
                s["charts"].append("performance")

    args.out.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "as_of": as_of.isoformat(),
        "source": "archive" if args.offline else "yahoo",
        "companies": summaries,
    }
    (args.out / "data.json").write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))

    # Remember names Yahoo told us so later runs can skip the slow info request.
    learned = {c.code: c.name for c in companies if c.name and not symbols.get(c.code)}
    if learned and not args.only:
        write_symbols(symbols_path, {**symbols, **learned})

    stale = sum(1 for c in companies if c.source == "archive")
    log.info("built %d symbols (%d from archive), %d failed, as of %s",
             len(summaries), stale, len(failed), as_of)
    return 0


if __name__ == "__main__":
    sys.exit(main())
