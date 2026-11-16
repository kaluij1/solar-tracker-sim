"""
Energy model: how much electricity does a standard residential PV system produce in a
typical year lying flat, at a fixed tilt, on a single axis tracker, or on a dual axis tracker?

Each step of the chain is done explicitly with pvlib, so every loss can be measured:

  weather (GHI, DNI, DHI, temperature, wind)
    -> 1. sun position
    -> 2. panel orientation (fixed, single axis tracker, dual axis tracker)
    -> 3. plane-of-array irradiance (light landing on the tilted panel, Perez sky model)
    -> 4. reflection losses at the glass (incidence angle modifier)
    -> 5. cell temperature (SAPM thermal model)
    -> 6. DC power (CEC single diode model, real module datasheet values)
    -> 7. system losses (soiling, wiring, mismatch... PVWatts default 14.08%)
    -> 8. AC power (Sandia inverter model, real inverter, includes clipping)
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd
import pvlib

# ---------------------------------------------------------------------------
# The "standard" system
# ---------------------------------------------------------------------------
MODULE_NAME = "Canadian_Solar_Inc__CS1U_400MS"          # 400 W mono-Si
INVERTER_NAME = "SMA_America__SB3_8_1SP_US_40__240V_"    # 3.85 kW AC
MODULES_PER_STRING = 6
STRINGS = 2
THERMAL = pvlib.temperature.TEMPERATURE_MODEL_PARAMETERS["sapm"]["open_rack_glass_polymer"]
SYSTEM_LOSSES = pvlib.pvsystem.pvwatts_losses()          # PVWatts defaults, 14.08 %

MODULE = pvlib.pvsystem.retrieve_sam("CECMod")[MODULE_NAME]
INVERTER = pvlib.pvsystem.retrieve_sam("CECInverter")[INVERTER_NAME]
N_MODULES = MODULES_PER_STRING * STRINGS
P_DC_STC_KW = MODULE["STC"] * N_MODULES / 1000            # nameplate DC size


# ---------------------------------------------------------------------------
# Weather
# ---------------------------------------------------------------------------
def load_tmy(path, year=2023):
    """Read an NSRDB typical meteorological year file.

    Handles both layouts: older files (as shipped with NREL SAM) are in local
    standard time, while files from the current NSRDB download are in UTC.
    Everything is converted to local standard time, and because a TMY stitches
    months from different real years, every row is given the same year.
    """
    weather, meta = pvlib.iotools.read_nsrdb_psm4(path, map_variables=True)
    local_offset = int(meta.get("Local Time Zone", meta["Time Zone"]))
    tz = f"Etc/GMT{-local_offset:+d}"                      # e.g. UTC-7 -> "Etc/GMT+7"
    location = pvlib.location.Location(
        latitude=meta["latitude"], longitude=meta["longitude"], tz=tz, altitude=meta["altitude"])

    local = weather.index.tz_convert(tz)
    # UTC files wrap: the first hours of 1 January UTC are the evening of 31 December local
    weather.index = pd.DatetimeIndex(
        [t.replace(year=year) for t in local.tz_localize(None)]).tz_localize(tz)
    weather = weather.sort_index()
    weather = weather[~weather.index.duplicated()]
    assert len(weather) == 8760, f"expected 8760 hours, got {len(weather)}"
    if "albedo" not in weather:                            # older files may not include it
        weather["albedo"] = 0.2
    return weather, location


# ---------------------------------------------------------------------------
# Panel orientation for each mounting type
# ---------------------------------------------------------------------------
def orientation_fixed(solpos, tilt, azimuth=180):
    n = len(solpos)
    return pd.Series(np.full(n, tilt, float), solpos.index), pd.Series(np.full(n, azimuth, float), solpos.index)


def orientation_single_axis(solpos, max_angle=60):
    """Horizontal north-south axis, rotating east to west (the utility-scale standard)."""
    t = pvlib.tracking.singleaxis(
        solpos["apparent_zenith"], solpos["azimuth"],
        axis_tilt=0, axis_azimuth=180, max_angle=max_angle, backtrack=False,
    )
    tilt = t["surface_tilt"].fillna(0)                   # parked flat at night
    azimuth = t["surface_azimuth"].fillna(180)
    return tilt, azimuth


def orientation_dual_axis(solpos, pointing_error_deg=0.0):
    """Two axis tracker. With no error the panel faces the sun exactly.

    pointing_error_deg tilts the panel that many degrees away from the sun (alternating
    above and below it hour by hour), so the beam always arrives at exactly that angle.
    Used to measure what an imperfect controller costs in energy.
    """
    zenith = solpos["apparent_zenith"]
    sign = np.where(np.arange(len(zenith)) % 2 == 0, 1.0, -1.0)
    tilt = (zenith + sign * pointing_error_deg).clip(lower=0, upper=90)
    azimuth = solpos["azimuth"]
    return tilt, azimuth


# ---------------------------------------------------------------------------
# The energy chain
# ---------------------------------------------------------------------------
def sandia_uncapped(v_dc, p_dc):
    """The Sandia inverter efficiency equation without the final clip at Paco.
    Used only to measure how much power the cap throws away."""
    inv = INVERTER
    dv = v_dc - inv["Vdco"]
    a = inv["Pdco"] * (1 + inv["C1"] * dv)
    b = inv["Pso"] * (1 + inv["C2"] * dv)
    c = inv["C0"] * (1 + inv["C3"] * dv)
    p_ac = (inv["Paco"] / (a - b) - c * (a - b)) * (p_dc - b) + c * (p_dc - b) ** 2
    return p_ac.where(p_dc > inv["Pso"], 0).clip(lower=0)


@dataclass
class Result:
    name: str
    hourly: pd.DataFrame        # every intermediate quantity, hour by hour

    def total(self, col):
        return self.hourly[col].sum() / 1000   # Wh -> kWh (or W/m2 -> kWh/m2)


def simulate(name, weather, location, tilt, azimuth, solpos):
    # 3. light landing on the panel
    dni_extra = pvlib.irradiance.get_extra_radiation(weather.index)
    airmass = pvlib.atmosphere.get_relative_airmass(solpos["apparent_zenith"])
    poa = pvlib.irradiance.get_total_irradiance(
        tilt, azimuth, solpos["apparent_zenith"], solpos["azimuth"],
        weather["dni"], weather["ghi"], weather["dhi"],
        dni_extra=dni_extra, airmass=airmass, albedo=weather["albedo"], model="perez",
    ).fillna(0)

    # 4. reflection off the glass: light arriving at a steep angle bounces off
    aoi = pvlib.irradiance.aoi(tilt, azimuth, solpos["apparent_zenith"], solpos["azimuth"])
    iam_beam = pvlib.iam.physical(aoi)
    # diffuse reflection depends only on tilt: compute it once per whole degree and look it up
    tilt_deg = tilt.round().astype(int)
    table = {t: pvlib.iam.marion_diffuse("physical", float(t)) for t in tilt_deg.unique()}
    iam_diffuse = {k: tilt_deg.map(lambda t: table[t][k]) for k in ("sky", "ground")}
    effective = (poa["poa_direct"] * iam_beam
                 + poa["poa_sky_diffuse"] * iam_diffuse["sky"]
                 + poa["poa_ground_diffuse"] * iam_diffuse["ground"]).fillna(0).clip(lower=0)

    # 5. cell temperature: sunlight heats the cells, wind cools them
    t_cell = pvlib.temperature.sapm_cell(
        poa["poa_global"], weather["temp_air"], weather["wind_speed"], **THERMAL)

    # 6. DC power from the single diode model, per module, then scaled to the array
    params = pvlib.pvsystem.calcparams_cec(
        effective, t_cell, MODULE["alpha_sc"], MODULE["a_ref"], MODULE["I_L_ref"],
        MODULE["I_o_ref"], MODULE["R_sh_ref"], MODULE["R_s"], MODULE["Adjust"])
    mpp = pvlib.pvsystem.max_power_point(*params, method="newton")
    p_dc_raw = (mpp["p_mp"].fillna(0) * N_MODULES).clip(lower=0)
    v_dc = mpp["v_mp"].fillna(0) * MODULES_PER_STRING

    # reference: what the array would make at its nameplate efficiency (25 C, no losses)
    p_dc_nameplate = effective / 1000 * P_DC_STC_KW * 1000

    # 7. system losses
    p_dc = p_dc_raw * (1 - SYSTEM_LOSSES / 100)

    # 8. inverter: DC -> AC, with efficiency curve and clipping at 3.85 kW
    p_ac = pvlib.inverter.sandia(v_dc, p_dc, INVERTER).clip(lower=0)
    clipped = (sandia_uncapped(v_dc, p_dc) - p_ac).clip(lower=0)   # power lost to the 3.85 kW cap

    hourly = pd.DataFrame({
        "ghi": weather["ghi"], "poa_global": poa["poa_global"], "poa_effective": effective,
        "t_air": weather["temp_air"], "t_cell": t_cell, "tilt": tilt, "azimuth": azimuth,
        "p_dc_nameplate": p_dc_nameplate, "p_dc_raw": p_dc_raw, "p_dc": p_dc,
        "p_ac": p_ac, "p_ac_clipped": clipped,
    })
    return Result(name, hourly)


def loss_waterfall(r: Result):
    """Energy at each stage of the chain, in kWh (irradiance stages in kWh/m2)."""
    h = r.hourly
    nameplate_poa = r.total("poa_global") * P_DC_STC_KW            # kWh if every photon became nameplate power
    stages = {
        "Light on panel x nameplate": nameplate_poa,
        "After glass reflection": r.total("poa_effective") * P_DC_STC_KW,
        "After heat and low light (DC)": r.total("p_dc_raw"),
        "After system losses (DC)": r.total("p_dc"),
        "After inverter (AC)": r.total("p_ac"),
    }
    return pd.Series(stages)


def summary(r: Result):
    ac = r.total("p_ac")
    return {
        "Light on panel (kWh/m2/yr)": r.total("poa_global"),
        "AC energy (kWh/yr)": ac,
        "Specific yield (kWh/kWp)": ac / P_DC_STC_KW,
        "Capacity factor (%)": 100 * ac / (P_DC_STC_KW * 8760),
        "Performance ratio (%)": 100 * ac / (r.total("poa_global") * P_DC_STC_KW),
        "Clipped energy (kWh/yr)": r.total("p_ac_clipped"),
        "Peak cell temp (C)": r.hourly["t_cell"].max(),
    }


def pvwatts_crosscheck(r: Result, weather):
    """Same light, but NREL's simpler PVWatts v5 equations for DC, temperature and inverter."""
    h = r.hourly
    t_cell = pvlib.temperature.sapm_cell(h["poa_global"], weather["temp_air"], weather["wind_speed"], **THERMAL)
    pdc0 = P_DC_STC_KW * 1000
    p_dc = pvlib.pvsystem.pvwatts_dc(h["poa_effective"], t_cell, pdc0, gamma_pdc=-0.0037)
    p_dc = p_dc * (1 - SYSTEM_LOSSES / 100)
    p_ac = pvlib.inverter.pvwatts(p_dc, pdc0=INVERTER["Paco"] / 0.96, eta_inv_nom=0.96)
    return p_ac.clip(lower=0).sum() / 1000
