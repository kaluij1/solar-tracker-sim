"""Check the model against a real PV system, not another model.

Data: PVDAQ system 4, a silicon array at NREL in Golden, Colorado, measured every minute
from 2010 to 2016 (AC power, sunlight on the panel, air temperature, wind speed), with
NSRDB satellite irradiance every 30 minutes for the same period. The file and the system
description (1 kW nominal, 40 degree tilt, facing south, temperature coefficient
-0.34 %/C) come from the RdTools example for this system:
https://github.com/NatLabRockies/rdtools/releases/download/3.0.0/pvdaq_system_4_2010-2016_subset_soil_signal.csv

Nothing is tuned. Losses are the same PVWatts defaults (14.08 %) used in the rest of this
repository, the inverter is a flat 96 %, and the model has no degradation.

Three tests:
  A. measured sunlight on the panel -> modeled AC power, against measured AC power
     (cell temperature, DC power, losses, inverter)
  B. satellite GHI/DNI/DHI -> modeled sunlight on the panel, against the measured value
     (sun position, Perez transposition)
  C. satellite GHI/DNI/DHI -> modeled AC power, against measured AC power (the whole chain)

Writes results/measured_validation.csv. The data file (114 MB) is downloaded on first run.
"""
from pathlib import Path
import urllib.request

import numpy as np
import pandas as pd
import pvlib

HERE = Path(__file__).parent
URL = ("https://github.com/NatLabRockies/rdtools/releases/download/3.0.0/"
       "pvdaq_system_4_2010-2016_subset_soil_signal.csv")
CACHE = HERE / "data" / "pvdaq_system_4.csv"

LAT, LON, TZ, ALT = 39.7406, -105.1774, "Etc/GMT+7", 1790   # altitude: approximate, Golden CO
TILT, AZIMUTH = 40, 180
PDC0, GAMMA = 1000.0, -0.0034
THERMAL = pvlib.temperature.TEMPERATURE_MODEL_PARAMETERS["sapm"]["open_rack_glass_polymer"]
LOSSES = pvlib.pvsystem.pvwatts_losses()
INVERTER_EFF = 0.96


def ac_power(effective, poa, temp_air, wind):
    t_cell = pvlib.temperature.sapm_cell(poa, temp_air, wind, **THERMAL)
    p_dc = pvlib.pvsystem.pvwatts_dc(effective, t_cell, PDC0, GAMMA) * (1 - LOSSES / 100)
    return p_dc.clip(lower=0) * INVERTER_EFF


def stats(model, measured):
    return {"model_over_measured": model.sum() / measured.sum(),
            "r2": np.corrcoef(model, measured)[0, 1] ** 2,
            "nrmse_pct": 100 * np.sqrt(((model - measured) ** 2).mean()) / measured.mean()}


def run():
    if not CACHE.exists():
        print("downloading", URL)
        urllib.request.urlretrieve(URL, CACHE)
    df = pd.read_csv(CACHE, index_col=0, parse_dates=True)
    df.index = df.index.tz_localize(TZ)

    # --- A: measured plane-of-array sunlight -> AC power, minute by minute, compared hourly
    m = df[["ac_power", "poa_irradiance", "ambient_temp", "wind_speed"]].copy()
    m = m[m.poa_irradiance.between(-5, 1500) & m.ambient_temp.between(-30, 50)]   # drop sensor glitches
    m["wind_speed"] = m.wind_speed.fillna(1.0).clip(lower=0)
    poa = m.poa_irradiance.clip(lower=0)
    m["model"] = ac_power(poa, poa, m.ambient_temp, m.wind_speed)
    hourly = m.resample("1h").agg(measured=("ac_power", "mean"), n=("ac_power", "count"),
                                  model=("model", "mean"), poa=("poa_irradiance", "mean"))
    hourly = hourly[hourly.n >= 55]                                             # complete hours only

    # --- B and C: satellite irradiance (30 minute) -> sunlight on the panel -> AC power
    s = df.dropna(subset=["ghi_nsrdb"]).copy()
    loc = pvlib.location.Location(LAT, LON, TZ, ALT)
    sp = loc.get_solarposition(s.index)
    t = pvlib.irradiance.get_total_irradiance(
        TILT, AZIMUTH, sp.apparent_zenith, sp.azimuth, s.dni_nsrdb, s.ghi_nsrdb, s.dhi_nsrdb,
        dni_extra=pvlib.irradiance.get_extra_radiation(s.index),
        airmass=pvlib.atmosphere.get_relative_airmass(sp.apparent_zenith), albedo=0.2, model="perez").fillna(0)
    aoi = pvlib.irradiance.aoi(TILT, AZIMUTH, sp.apparent_zenith, sp.azimuth)
    diffuse = pvlib.iam.marion_diffuse("physical", TILT)
    effective = (t.poa_direct * pvlib.iam.physical(aoi) + t.poa_sky_diffuse * diffuse["sky"]
                 + t.poa_ground_diffuse * diffuse["ground"]).clip(lower=0)
    s["poa_model"] = t.poa_global
    s["model"] = ac_power(effective, t.poa_global, s.ambient_temp_nsrdb, 1.0)    # no satellite wind in the file
    # measured values averaged over the same 30 minutes, centered on the satellite time stamp
    half = df[["poa_irradiance", "ac_power"]].resample("30min", offset="15min").agg(["mean", "count"])
    half.index = half.index + pd.Timedelta("15min")
    s["poa_measured"], s["measured"], s["n"] = half[("poa_irradiance", "mean")], half[("ac_power", "mean")], half[("ac_power", "count")]
    s = s[s.n >= 28].dropna(subset=["poa_measured", "measured", "model"])

    rows = []
    def add(test, label, model, measured, hours):
        rows.append({"test": test, "period": label, "hours": hours, **stats(model, measured)})
    for label, hh, ss in [("2010-2016", hourly, s)] + [(str(y), hourly[hourly.index.year == y], s[s.index.year == y]) for y in range(2010, 2017)]:
        add("A: measured sunlight on panel -> AC power", label, hh.model, hh.measured, len(hh))
        add("B: satellite irradiance -> sunlight on panel", label, ss.poa_model, ss.poa_measured, len(ss) / 2)
        add("C: satellite irradiance -> AC power", label, ss.model, ss.measured, len(ss) / 2)
    out = pd.DataFrame(rows)
    out.to_csv(HERE / "results" / "measured_validation.csv", index=False)
    return out


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    print(run().round(3).to_string(index=False))
