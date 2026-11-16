"""Single axis trackers in rows: what row-to-row shading costs, and what backtracking saves.

run_energy.py models one tracker standing alone. On a solar farm the trackers stand in
rows, and when the sun is low each row's shadow reaches the next one. This script reruns
the single axis case for a range of row spacings and three situations:

  alone          no neighbors (the run_energy.py result)
  true tracking  rows keep pointing at the sun and shade each other
  backtracking   rows turn back toward flat so that no shadow reaches the next row

Fixed-tilt energy is taken from summary.csv, so gains are measured against the same baseline.
Only the direct beam is shaded here; the neighbors also hide part of the sky and the ground
from each row, which is not modeled.

The last column repeats the solar farm break-even from economics.py (same price, upkeep,
discount rate and life) with the energy of each case.

Run run_energy.py first. Writes results/rows.csv.
"""
from pathlib import Path

import pandas as pd

import economics
import energy_model as em

HERE = Path(__file__).parent
DATA = HERE / "data"
OUT = HERE / "results"

SITES = {
    "Phoenix, AZ": DATA / "nsrdb" / "phoenix_tmy-2025.csv",
    "Des Moines, IA": DATA / "des_moines_ia_41.586835_-93.624959_psmv3_60_tmy.csv",
}
GCRS = [0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]


def run():
    summary = pd.read_csv(OUT / "summary.csv")
    pvf, farm = economics.present_value_factor(), economics.MARKETS["Utility scale"]
    rows = []
    for site, path in SITES.items():
        weather, location = em.load_tmy(path)
        solpos = location.get_solarposition(weather.index, pressure=weather["pressure"] * 100,
                                            temperature=weather["temp_air"])
        s = summary[summary.site == site].set_index("setup")
        fixed = s.loc["Fixed, best tilt", "AC energy (kWh/yr)"]
        alone = s.loc["Single axis", "AC energy (kWh/yr)"]
        for gcr in GCRS:
            cases = {
                "True tracking, linear shade loss": dict(backtrack=False, shade_model="linear"),
                "True tracking, bypass block loss": dict(backtrack=False, shade_model="martinez"),
                "Backtracking": dict(backtrack=True, shade_model="linear"),
            }
            for case, kw in cases.items():
                tilt, az, fs, beam = em.single_axis_in_rows(solpos, gcr, **kw)
                r = em.simulate(case, weather, location, tilt, az, solpos, beam_factor=beam)
                ac = r.total("p_ac")
                daylight = solpos["apparent_zenith"] < 90
                extra_kwh_per_kw = (ac - fixed) / em.P_DC_STC_KW
                rows.append({
                    "site": site, "gcr": gcr, "case": case, "ac_kwh": ac,
                    "utility_breakeven_premium_per_w": pvf * (extra_kwh_per_kw * farm["energy_value"] - farm["extra_om"]) / 1000,
                    "gain_vs_fixed_pct": 100 * (ac / fixed - 1),
                    "vs_tracker_alone_pct": 100 * (ac / alone - 1),
                    "daylight_hours_with_shade_pct": 100 * (fs[daylight] > 0).mean(),
                })
    out = pd.DataFrame(rows)
    out.to_csv(OUT / "rows.csv", index=False)
    return out


if __name__ == "__main__":
    out = run()
    pd.set_option("display.width", 200)
    print(out.round(2).to_string(index=False))
