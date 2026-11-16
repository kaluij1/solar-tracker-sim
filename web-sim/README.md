# Live simulator (runs in the browser)

An interactive version of this project's energy model and controller simulation.
Open `solar-sim.html` in any browser. No install, no server.

- **Energy:** pick Phoenix or Des Moines, a day and a time. The sun follows its real path,
  the weather is the site's hourly NSRDB typical-year data,[^nsrdb] and four setups (flat,
  fixed at the best tilt, single axis, dual axis) turn and produce power. A full year is
  also computed in the browser, about 0.3 s, and shown next to the pvlib results.
- **Solar farm:** a side view of tracker rows shading each other, with a switch between
  pointing at the sun and backtracking, an adjustable row spacing, and a full year computed
  for each.
- **Payback:** how much extra a tracker can cost and still pay for itself, with sliders for
  electricity price, tracker cost, upkeep, discount rate and system life. The starting
  values are the ones in `energy-yield/economics.py`.
- **Controller replay:** the single axis tracker's sensors, divider wall and servo, ported
  from the Wokwi chip (`single-axis/wokwi`). Turn up clouds and flicker and compare the
  original controller, the moving average with a deadband, and a calculated sun position.

## Files

| File | What it is |
|---|---|
| `solar-sim.html`, `style.css` | The page (the same page as on my website) |
| `scene3d.js` | The 3D view (three.js, loaded from a CDN). Drawing only: every angle and number comes from `solar-model.js`. Without WebGL the page falls back to a flat drawing |
| `solar-model.js` | The physics, ported from `energy-yield/energy_model.py` |
| `controller-model.js` | The tracker and its controllers, ported from the Wokwi chip and sketch |
| `weather-data.js` | Hourly weather for both sites, plus module, inverter and loss parameters, exported from the pvlib model |
| `validate.js` | Checks this model against pvlib and writes `validation.json` |
| `check-sun.json` | pvlib sun positions (NREL SPA) used by `validate.js` |
| `check-rows.json`, `export_rows_reference.py` | pvlib tracker angles, shaded fractions and yearly energy for trackers in rows, and the script that writes them |

## The model, step by step

1. **Sun position:** NOAA solar calculator equations, based on Meeus.[^noaa] The pvlib model
   uses NREL's SPA.[^spa]
2. **Panel orientation:** the same rules as `energy_model.py` (single axis: horizontal
   north-south axis, ±60°, no backtracking).
3. **Light on the panel:** direct beam, Perez sky diffuse,[^perez] ground reflection.
4. **Reflection losses:** physical incidence angle model[^desoto] and Marion's diffuse
   correction,[^marion] with the table exported from pvlib.
   For trackers in rows: the backtracking angle of Anderson and Mikofski[^bt] and the shaded
   fraction of Anderson and Jensen;[^aj] shade loss either in proportion to area or by
   bypass block (Martínez-Moreno et al.).[^mm]
5. **Cell temperature:** Sandia (SAPM) model, open rack glass/polymer.[^sapm]
6. **Power:** PVWatts DC with the module's own temperature coefficient, 14.08% losses, and
   the PVWatts inverter, clipped at 3,850 W.[^pvwatts]

The one simplification: `energy_model.py` uses the CEC single diode module model and the
Sandia inverter model;[^sandia] this page uses the lighter PVWatts equations for both.
Between hours, the weather is interpolated linearly.

## Validation

```
node validate.js
```

Results (`validation.json`):

| Check | Result |
|---|---|
| Sun position vs NREL SPA, every 5th daylight hour | max error 0.024° zenith, 0.028° azimuth |
| Annual energy vs full pvlib model, 2 sites × 4 setups | all within 0.57% (the browser model reads slightly low) |
| Trackers in rows: rotation angle vs `pvlib.tracking.singleaxis`, with and without backtracking | max error 0.12° |
| Trackers in rows: shaded fraction vs `pvlib.shading.shaded_fraction1d` | max error 0.003 |
| Trackers in rows: annual energy vs pvlib, 2 sites × 9 row spacings × 3 cases | all 54 within 0.52% |
| Tracking gain over fixed tilt, Phoenix | single axis 24.8% (pvlib 25.0%), dual axis 39.6% (pvlib 39.6%) |
| Tracking gain over fixed tilt, Des Moines | single axis 17.6% (pvlib 17.8%), dual axis 34.5% (pvlib 34.7%) |

The controller port reproduces the C test (`single-axis/tests`): with 30% cloud and 10%
flicker, the original controller makes about 1,800 servo moves with over 400 reversals in
a 120 s sweep, the filtered one about 160 moves with a handful of reversals, and the
calculated one about 80 moves with 1 reversal (averages of 5 runs; the noise is random).
The noise levels and divider wall geometry are assumptions, listed in the main README.

Source numbers match [SOURCES.md](../SOURCES.md).

[^nsrdb]: SOURCES.md #21.
[^noaa]: SOURCES.md #35.
[^spa]: SOURCES.md #9.
[^perez]: SOURCES.md #10.
[^desoto]: SOURCES.md #11.
[^marion]: SOURCES.md #12.
[^sapm]: SOURCES.md #13.
[^pvwatts]: SOURCES.md #16.
[^sandia]: SOURCES.md #15.
[^bt]: SOURCES.md #7.
[^aj]: SOURCES.md #36.
[^mm]: SOURCES.md #37.
