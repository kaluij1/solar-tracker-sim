"""Value, not energy: what is each mounting choice's output worth at real hourly prices?

Everything else in this folder values a kWh the same at noon and at 7 pm. In California
that is no longer true: midday prices are often near or below zero. This script prices
each hour of output with CAISO's 2025 day-ahead prices at the SP15 hub (Southern
California) and asks whether tracking's extra morning and evening output is worth more
than its share of energy suggests.

Site: Daggett, California (Mojave Desert, inside the SP15 area), NSRDB typical year as
shipped with NREL SAM. Weather is a typical year and prices are 2025, so the two are
matched by month, day and hour, not by actual cloudy days (see README).

Setups, per kW of panels:
  Fixed, best tilt, facing south   the baseline
  Fixed, best tilt, facing west    a cheap way to move output toward evening
  Single axis, standing alone
  Single axis in rows, backtracking (GCR 0.35)
  Dual axis

For each: energy, market revenue, revenue if the plant stops when the price is below
zero, capture price (revenue / energy) and value factor (capture price / average price
of all hours), and the break-even tracker premium two ways:
  1. flat $30/MWh contract price (energy only, as in economics.py)
  2. 2025 market revenue (what a plant selling at hourly prices would earn)

Run run_energy.py first. Writes results/value.csv and results/value_by_hour.csv.
Price data: data/caiso_sp15_dam_2025.csv, from fetch_caiso_prices.py.
"""
from pathlib import Path

import numpy as np
import pandas as pd

import economics
import energy_model as em

HERE = Path(__file__).parent
DATA, OUT = HERE / "data", HERE / "results"
WEATHER = DATA / "daggett_ca_34.865371_-116.783023_psmv3_60_tmy.csv"
PRICES = DATA / "caiso_sp15_dam_2025.csv"
GCR = 0.35
PREMIUM_LIKE_FOR_LIKE = 0.11          # $/W DC, SEIA / Wood Mackenzie Q2 2026
FLAT_PPA = 30.0                       # $/MWh, the flat contract price used elsewhere
OM = economics.MARKETS["Utility scale"]["extra_om"]


def load_prices(weather_index):
    p = pd.read_csv(PRICES)
    start = pd.to_datetime(p["Interval Start"], utc=True).dt.tz_convert("Etc/GMT+8")   # Pacific standard time
    p["key"] = start.dt.strftime("%m-%d %H")
    p = p.drop_duplicates("key").set_index("key")["LMP"]
    keys = weather_index.strftime("%m-%d %H")
    prices = pd.Series(p.reindex(keys).values, index=weather_index)
    missing = prices.isna().sum()
    return prices.interpolate(limit_direction="both"), missing


def run():
    weather, location = em.load_tmy(WEATHER)
    solpos = location.get_solarposition(weather.index, pressure=weather["pressure"] * 100,
                                        temperature=weather["temp_air"])
    prices, missing = load_prices(weather.index)                 # $/MWh = $ per 1000 kWh

    sweep = {}
    for tilt in range(0, 61, 2):
        t, a = em.orientation_fixed(solpos, tilt)
        sweep[tilt] = em.simulate("", weather, location, t, a, solpos).total("p_ac")
    best = int(pd.Series(sweep).idxmax())

    cases = {
        "Fixed, best tilt, facing south": (em.orientation_fixed(solpos, best, 180), None),
        "Fixed, best tilt, facing west": (em.orientation_fixed(solpos, best, 270), None),
        "Single axis, standing alone": (em.orientation_single_axis(solpos), None),
    }
    tilt, az, _, beam = em.single_axis_in_rows(solpos, GCR, backtrack=True, shade_model="linear")
    cases[f"Single axis in rows, backtracking (GCR {GCR})"] = ((tilt, az), beam)
    cases["Dual axis"] = (em.orientation_dual_axis(solpos), None)

    kw = em.P_DC_STC_KW
    pvf = economics.present_value_factor()
    avg_price = prices.mean()
    rows, by_hour = [], {}
    for name, ((t, a), beam) in cases.items():
        p_ac = em.simulate(name, weather, location, t, a, solpos, beam_factor=beam).hourly["p_ac"] / 1000   # kWh each hour
        energy = p_ac.sum() / kw
        revenue = (p_ac * prices).sum() / 1000 / kw                    # $ per kW per year
        revenue_stop = (p_ac * prices.clip(lower=0)).sum() / 1000 / kw
        rows.append({"setup": name, "kwh_per_kw": energy, "market_revenue_per_kw": revenue,
                     "revenue_stop_below_zero_per_kw": revenue_stop,
                     "capture_price_per_mwh": 1000 * revenue / energy,
                     "value_factor": (1000 * revenue / energy) / avg_price,
                     "flat_ppa_revenue_per_kw": energy * FLAT_PPA / 1000,
                     "share_of_energy_in_negative_hours_pct": 100 * p_ac[prices < 0].sum() / p_ac.sum()})
        by_hour[name] = p_ac.groupby(p_ac.index.hour).sum() / kw
    df = pd.DataFrame(rows).set_index("setup")
    base = df.loc["Fixed, best tilt, facing south"]
    df["energy_gain_pct"] = 100 * (df.kwh_per_kw / base.kwh_per_kw - 1)
    df["revenue_gain_pct"] = 100 * (df.market_revenue_per_kw / base.market_revenue_per_kw - 1)
    df["breakeven_flat_ppa_per_w"] = pvf * ((df.kwh_per_kw - base.kwh_per_kw) * FLAT_PPA / 1000 - OM) / 1000
    df["breakeven_market_per_w"] = pvf * ((df.market_revenue_per_kw - base.market_revenue_per_kw) - OM) / 1000
    df["breakeven_market_stop_below_zero_per_w"] = pvf * ((df.revenue_stop_below_zero_per_kw - base.revenue_stop_below_zero_per_kw) - OM) / 1000
    df.loc["Fixed, best tilt, facing south", ["breakeven_flat_ppa_per_w", "breakeven_market_per_w",
           "breakeven_market_stop_below_zero_per_w"]] = np.nan
    df["best_tilt_deg"] = best
    df.to_csv(OUT / "value.csv")

    h = pd.DataFrame(by_hour)
    h["avg_price_per_mwh"] = prices.groupby(prices.index.hour).mean()
    h.rename_axis("hour_pst").to_csv(OUT / "value_by_hour.csv")

    info = {"average_price": avg_price, "hours_below_zero_pct": 100 * (prices < 0).mean(),
            "missing_price_hours": int(missing), "best_tilt": best}
    return df, h, info


if __name__ == "__main__":
    df, h, info = run()
    pd.set_option("display.width", 250)
    print(info)
    print(df.round(3).T.to_string())
    print(h.round(2).to_string())
