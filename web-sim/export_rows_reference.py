"""Write check-rows.json: pvlib reference values for trackers in rows, used by validate.js.

  cd energy-yield && python run_energy.py && python run_rows.py
  cd ../web-sim && python export_rows_reference.py && node validate.js
"""
import json
import sys
from pathlib import Path

import pandas as pd
import pvlib

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "energy-yield"))
import energy_model as em   # noqa: E402
import run_rows as rr       # noqa: E402

GCR = 0.35
ref = {}
for site, path in rr.SITES.items():
    weather, location = em.load_tmy(path)
    solpos = location.get_solarposition(weather.index, pressure=weather["pressure"] * 100,
                                        temperature=weather["temp_air"])
    samples = []
    for backtrack in (False, True):
        t = pvlib.tracking.singleaxis(solpos["apparent_zenith"], solpos["azimuth"], axis_tilt=0,
                                      axis_azimuth=180, max_angle=60, backtrack=backtrack, gcr=GCR)
        _, _, shaded, _ = em.single_axis_in_rows(solpos, GCR, backtrack, shade_model="linear")
        for i in range(0, 8760, 7):
            if solpos["apparent_zenith"].iloc[i] < 89:
                samples.append([i, int(backtrack), round(float(t["tracker_theta"].iloc[i]), 4),
                                round(float(shaded.iloc[i]), 5)])
    ref[site] = {"gcr": GCR, "samples": samples}

rows = pd.read_csv(HERE.parent / "energy-yield" / "results" / "rows.csv")
ref["annual"] = [{"site": r.site, "gcr": r.gcr, "case": r.case, "pvlib_kwh": round(r.ac_kwh, 1)}
                 for r in rows.itertuples()]
json.dump(ref, open(HERE / "check-rows.json", "w"), separators=(",", ":"))
print("wrote check-rows.json")
