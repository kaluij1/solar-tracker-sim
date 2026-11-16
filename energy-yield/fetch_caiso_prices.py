"""Download one year of hourly day-ahead electricity prices for Southern California.

Prices are CAISO's day-ahead locational marginal prices (LMP) at the SP15 trading hub,
which covers Southern California's desert solar region. They come from CAISO's public
OASIS site through the open source gridstatus library. No account is needed.

    pip install gridstatus pandas
    python fetch_caiso_prices.py

It asks OASIS for one month at a time and pauses between requests (OASIS limits how
fast you can ask), so a full year takes several minutes. Writes data/caiso_sp15_dam_2025.csv.
"""
from pathlib import Path
import warnings

import pandas as pd
import gridstatus

YEAR = 2025
HUB = "TH_SP15_GEN-APND"           # Southern California trading hub
OUT = Path(__file__).parent / "data" / f"caiso_sp15_dam_{YEAR}.csv"


def main():
    caiso = gridstatus.CAISO()
    parts = []
    for month in range(1, 13):
        start = pd.Timestamp(year=YEAR, month=month, day=1)
        end = start + pd.offsets.MonthBegin(1)
        print(f"{start:%b %Y} ...", flush=True)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)   # get_lmp still works for one hub
            df = caiso.get_lmp(date=start, end=end, market="DAY_AHEAD_HOURLY",
                               locations=[HUB], sleep=5)
        parts.append(df)
    prices = pd.concat(parts, ignore_index=True)
    keep = [c for c in ["Interval Start", "Interval End", "Location", "LMP",
                        "Energy", "Congestion", "Loss"] if c in prices.columns]
    prices = prices[keep].drop_duplicates(subset=["Interval Start"]).sort_values("Interval Start")
    OUT.parent.mkdir(exist_ok=True)
    prices.to_csv(OUT, index=False)

    lmp = prices["LMP"]
    print(f"\nWrote {OUT} ({len(prices)} hours; a full year is 8,760)")
    print(f"Average price ${lmp.mean():.1f}/MWh, {100 * (lmp < 0).mean():.1f}% of hours below $0")


if __name__ == "__main__":
    main()
