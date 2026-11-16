"""Which tracker cost should a solar farm compare against, and does the answer change?

Three published numbers for how much more a single axis tracker costs than a fixed rack
measure different things:

  $0.01/W DC  Berkeley Lab, 2025 projects: average installed cost of real tracking projects
              minus real fixed-tilt projects. Different projects, different sizes, regions and
              equipment; the report says it "does not control for other factors".
  $0.11/W DC  SEIA / Wood Mackenzie, Q2 2026: modeled ("bottoms-up") national average price of
              the same kind of system built both ways. A like-for-like comparison.
  $0.20/W DC  Berkeley Lab 2023 data, as used in NREL's Q1 2024 benchmark. Older.

This script compares each with the break-even premium (economics.py's formula) for a tracker
standing alone and for trackers in rows with backtracking (run_rows.py), across the range of
contract prices Berkeley Lab reports ($25 to $35/MWh) and three discount rates.

Run run_energy.py and run_rows.py first. Writes results/cost_check.csv.
"""
from pathlib import Path

import pandas as pd

import economics
import energy_model as em

RES = Path(__file__).parent / "results"
PREMIUMS = {"LBNL 2025 projects": 0.01, "SEIA/WoodMac Q2 2026 model": 0.11, "LBNL 2023 data": 0.20}
PRICES = [0.025, 0.030, 0.035]          # $/kWh
RATES = [0.04, 0.06, 0.08]
GCR = 0.35
OM = economics.MARKETS["Utility scale"]["extra_om"]


def run():
    summary = pd.read_csv(RES / "summary.csv")
    rows = pd.read_csv(RES / "rows.csv")
    out = []
    for site, s in summary.groupby("site"):
        s = s.set_index("setup")
        fixed = s.loc["Fixed, best tilt", "AC energy (kWh/yr)"]
        cases = {
            "Single axis, standing alone": s.loc["Single axis", "AC energy (kWh/yr)"],
            f"Single axis in rows, backtracking (GCR {GCR})":
                rows[(rows.site == site) & (rows.case == "Backtracking") & (rows.gcr.round(2) == GCR)].ac_kwh.iloc[0],
        }
        for case, ac in cases.items():
            extra = (ac - fixed) / em.P_DC_STC_KW            # kWh per kW DC per year
            for price in PRICES:
                for rate in RATES:
                    be = economics.present_value_factor(rate=rate) * (extra * price - OM) / 1000
                    row = {"site": site, "case": case, "gain_vs_fixed_pct": 100 * (ac / fixed - 1),
                           "price_per_mwh": price * 1000, "discount_rate_pct": rate * 100,
                           "breakeven_premium_per_w": be}
                    for name, p in PREMIUMS.items():
                        row[f"pays_at_{p:.2f}"] = be >= p
                    out.append(row)
    df = pd.DataFrame(out)
    df.to_csv(RES / "cost_check.csv", index=False)
    return df


if __name__ == "__main__":
    df = run()
    pd.set_option("display.width", 220)
    base = df[(df.price_per_mwh == 30) & (df.discount_rate_pct == 6)]
    print(base.round(3).to_string(index=False))
    print()
    g = df.groupby(["site", "case"]).breakeven_premium_per_w.agg(["min", "max"]).round(3)
    g["pays_at_0.11_in"] = df.groupby(["site", "case"])["pays_at_0.11"].mean().map(lambda x: f"{x:.0%} of 9 cases")
    print(g.to_string())
