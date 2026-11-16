"""Run the energy model for every site and setup, and save the results.

Outputs (results/):
  summary.csv            one row per site and setup: energy, yield, gains
  monthly.csv            monthly AC energy per site and setup
  waterfall.csv          energy left after each step of the model chain
  tilt_sweep.csv         fixed-tilt energy from 0 to 60 degrees per site
  daily_profiles.csv     hourly AC power on 21 June and 21 December per site
  dataset_check.csv      Phoenix results across five versions of the TMY data
  pointing_error.csv     dual axis energy loss vs pointing error (Phoenix)
"""
from pathlib import Path

import pandas as pd

import energy_model as em

HERE = Path(__file__).parent
DATA = HERE / "data"
OUT = HERE / "results"
OUT.mkdir(exist_ok=True)

SITES = {
    "Phoenix, AZ": DATA / "nsrdb" / "phoenix_tmy-2025.csv",
    "Des Moines, IA": DATA / "des_moines_ia_41.586835_-93.624959_psmv3_60_tmy.csv",
}
SETUPS = ["Flat", "Fixed, best tilt", "Single axis", "Dual axis"]


def solar_position(weather, location):
    return location.get_solarposition(weather.index, pressure=weather["pressure"] * 100,
                                      temperature=weather["temp_air"])


def run_site(path):
    weather, location = em.load_tmy(path)
    solpos = solar_position(weather, location)

    sweep = {}
    for tilt in range(0, 61, 2):
        t, a = em.orientation_fixed(solpos, tilt)
        sweep[tilt] = em.simulate(f"fixed {tilt}", weather, location, t, a, solpos).total("p_ac")
    sweep = pd.Series(sweep)
    best_tilt = int(sweep.idxmax())

    orientations = {
        "Flat": em.orientation_fixed(solpos, 0),
        "Fixed, best tilt": em.orientation_fixed(solpos, best_tilt),
        "Single axis": em.orientation_single_axis(solpos),
        "Dual axis": em.orientation_dual_axis(solpos),
    }
    results = {name: em.simulate(name, weather, location, t, a, solpos)
               for name, (t, a) in orientations.items()}
    return weather, location, solpos, sweep, best_tilt, results


summary_rows, monthly, waterfall, sweeps, daily = [], {}, {}, {}, {}
for site, path in SITES.items():
    weather, location, solpos, sweep, best_tilt, results = run_site(path)
    sweeps[site] = sweep
    fixed_ac = results["Fixed, best tilt"].total("p_ac")
    flat_ac = results["Flat"].total("p_ac")
    diffuse_share = weather["dhi"].sum() / weather["ghi"].sum()
    for name, r in results.items():
        row = {"site": site, "setup": name, "best_tilt_deg": best_tilt,
               "lat": location.latitude, "ghi_kwh_m2": weather["ghi"].sum() / 1000,
               "diffuse_share": diffuse_share}
        row.update(em.summary(r))
        row["Gain vs flat (%)"] = 100 * (r.total("p_ac") / flat_ac - 1)
        row["Gain vs fixed (%)"] = 100 * (r.total("p_ac") / fixed_ac - 1)
        row["PVWatts cross-check (kWh/yr)"] = em.pvwatts_crosscheck(r, weather)
        summary_rows.append(row)
        m = r.hourly["p_ac"].resample("ME").sum() / 1000
        monthly[(site, name)] = m.values
        waterfall[(site, name)] = em.loss_waterfall(r)
        for day in ("2023-06-21", "2023-12-21"):
            daily[(site, name, day)] = (r.hourly["p_ac"].loc[day] / 1000).values

summary = pd.DataFrame(summary_rows)
summary.to_csv(OUT / "summary.csv", index=False)
pd.DataFrame(monthly, index=pd.date_range("2023-01", periods=12, freq="MS").strftime("%b")).to_csv(OUT / "monthly.csv")
pd.DataFrame(waterfall).to_csv(OUT / "waterfall.csv")
pd.DataFrame(sweeps).rename_axis("tilt_deg").to_csv(OUT / "tilt_sweep.csv")
pd.DataFrame(daily, index=range(24)).rename_axis("hour").to_csv(OUT / "daily_profiles.csv")

# --- Phoenix: how much do the answers change with the version of the weather data? ---
check = []
versions = {"SAM sample (PSM v3)": DATA / "phoenix_az_33.450495_-111.983688_psmv3_60_tmy.csv"}
versions.update({f"NSRDB tmy-{y}": DATA / "nsrdb" / f"phoenix_tmy-{y}.csv" for y in (2022, 2023, 2024, 2025)})
versions["NSRDB tdy-2025 (direct-weighted)"] = DATA / "nsrdb" / "phoenix_tdy-2025.csv"
for label, path in versions.items():
    weather, location, solpos, sweep, best_tilt, results = run_site(path)
    fixed = results["Fixed, best tilt"].total("p_ac")
    check.append({"dataset": label, "ghi_kwh_m2": weather["ghi"].sum() / 1000, "best_tilt_deg": best_tilt,
                  **{f"{k} (kWh/yr)": r.total("p_ac") for k, r in results.items()},
                  "Single axis gain vs fixed (%)": 100 * (results["Single axis"].total("p_ac") / fixed - 1),
                  "Dual axis gain vs fixed (%)": 100 * (results["Dual axis"].total("p_ac") / fixed - 1)})
pd.DataFrame(check).to_csv(OUT / "dataset_check.csv", index=False)

# --- Phoenix: what does pointing error cost a dual axis tracker? ---
weather, location = em.load_tmy(SITES["Phoenix, AZ"])
solpos = solar_position(weather, location)
perfect = None
rows = []
for err in [0, 1, 2, 3, 4, 5, 7.5, 10, 15, 20, 30]:
    t, a = em.orientation_dual_axis(solpos, pointing_error_deg=err)
    ac = em.simulate(f"dual {err}", weather, location, t, a, solpos).total("p_ac")
    perfect = perfect or ac
    rows.append({"pointing_error_deg": err, "ac_kwh": ac, "loss_pct": 100 * (1 - ac / perfect)})
pd.DataFrame(rows).to_csv(OUT / "pointing_error.csv", index=False)

pd.set_option("display.width", 200)
cols = ["site", "setup", "best_tilt_deg", "AC energy (kWh/yr)", "Specific yield (kWh/kWp)",
        "Capacity factor (%)", "Gain vs flat (%)", "Gain vs fixed (%)", "PVWatts cross-check (kWh/yr)"]
print(summary[cols].round(1).to_string(index=False), "\n")
print(pd.DataFrame(check).round(1).to_string(index=False), "\n")
print(pd.DataFrame(rows).round(2).to_string(index=False))
