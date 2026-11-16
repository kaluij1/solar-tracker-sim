"""Stage 2: what does the tracking controller cost in energy and in motor wear?

Combines two results:
  results/pointing_error.csv  annual energy loss of a dual axis tracker vs pointing error (Phoenix)
  results/hil_dual_axis.csv   pointing error and motor activity of each controller, measured in
                              the hardware-in-the-loop simulation (dual-axis/tests, --csv)
Writes results/controller_energy.csv.
"""
from pathlib import Path

import numpy as np
import pandas as pd

RES = Path(__file__).parent / "results"

curve = pd.read_csv(RES / "pointing_error.csv")
hil = pd.read_csv(RES / "hil_dual_axis.csv")
perfect_kwh = curve.loc[curve.pointing_error_deg == 0, "ac_kwh"].iloc[0]

hil["annual_loss_pct"] = np.interp(hil.mean_error_deg, curve.pointing_error_deg, curve.loss_pct)
hil["annual_loss_kwh"] = hil.annual_loss_pct / 100 * perfect_kwh
hil["total_moves"] = hil.pan_moves + hil.tilt_moves
hil["total_reversals"] = hil.pan_reversals + hil.tilt_reversals
baseline = hil.loc[hil.scenario.str.contains("calculated"), "total_moves"].iloc[0]
hil["moves_vs_calculated"] = hil.total_moves / baseline
hil.to_csv(RES / "controller_energy.csv", index=False)

pd.set_option("display.width", 200)
print(hil[["scenario", "mean_error_deg", "annual_loss_pct", "annual_loss_kwh",
           "total_moves", "total_reversals", "moves_vs_calculated"]].round(2).to_string(index=False))
