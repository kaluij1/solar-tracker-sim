# Is Solar Tracking Worth It?

**From a twitching student prototype to a question the solar industry actually asks, and an answer that turned out much closer than the industry's choices suggest.**

In my second year at St. Olaf, I worked on a team of five building a dual axis solar
tracker: four photoresistors, two servos, and an Arduino that turned the panel toward
the brighter side. It worked under a lamp, then twitched constantly outdoors, because
cloud and reflection noise was bigger than the threshold we had tuned indoors. We fixed
it with a moving average and a deadband sized from measured noise.[^me]

The field logs from that project were lost, so this repository rebuilds it in two parts:

1. **The controller,** as a hardware-in-the-loop simulation. Real Arduino firmware runs on a simulated ATmega328P in [Wokwi](https://wokwi.com),[^wokwi-uno] against a custom simulated chip[^wokwi-chips] that models the sun, the servos, the photoresistors, clouds and reflections.
2. **The bigger question,** as an energy and economics model built with pvlib:[^pvlib] how much extra energy do tilt and tracking produce in a sunny desert and in the cloudier Midwest, and does that extra energy pay for the tracker, for a home and for a solar farm?

> **How claims are backed.** Every number and statement here is one of three things:
> a published source (footnoted), a result produced by this repository (footnoted with
> the file that holds it), or an assumption (labeled as one, with the reasoning). The
> full reference list is in [`SOURCES.md`](SOURCES.md).

**Checked against a real array.** Run against 7 years of measured output from an NREL test
array in Golden, Colorado, with nothing tuned, the model predicts total energy from
satellite weather within 2% (1.9% low), and within 1% when given the measured sunlight on
the panel. Single hours are far less certain. Details in
[`energy-yield/README.md`](energy-yield/README.md#5-checked-against-a-real-system).

**Try it in a browser:** [`web-sim/`](web-sim/) is an interactive version of both parts.
Open `web-sim/solar-sim.html` to watch four panel setups follow the sun on any day, and to
replay the twitching controller with adjustable clouds and flicker. It also shows rows of trackers shading each other and backtracking, and has a payback calculator with adjustable prices. The controller can also run on a real day of weather: in Phoenix on 21 June the original controller reverses about 14,000 times an hour yet loses only 0.05% of the energy, so the real cost of twitching is servo movement, not power. Its physics agrees
with the pvlib model within 0.57% over a full year (see [`web-sim/README.md`](web-sim/README.md)).

## The answer

| | Phoenix, AZ | Des Moines, IA |
|---|---|---|
| Fixed tilt vs flat | +15% | +21% |
| Single axis tracking vs fixed tilt | +25% | +18% |
| Dual axis tracking vs fixed tilt | +40% | +35% |
| Tracker on a home | Does not pay off | Does not pay off |
| Single axis tracker on a solar farm, rows with backtracking | Roughly even, on energy alone: worth $0.10/W vs a $0.11/W like-for-like price | No: worth $0.03/W |

Energy rows: [`energy-yield/results/summary.csv`](energy-yield/results/summary.csv). Verdicts: [`energy-yield/results/economics.csv`](energy-yield/results/economics.csv) and [`energy-yield/results/cost_check.csv`](energy-yield/results/cost_check.csv).

* **Tilting adds a lot of energy, and it added more at the more northern site** (+21% in Des Moines vs +15% in Phoenix).[^r-summary] This fits the textbook result that a fixed panel collects the most energy over a year when tilted at about the site's latitude.[^pvedu-tilt]
* **Trackers don't pay off on homes.** In Phoenix the extra energy justifies at most $0.57/W extra for a single axis tracker over 25 years,[^r-econ] but trackers add 40 to 100% to a system's cost,[^es-trackers] which is $1.26 to $3.15/W on a $3.15/W home system.[^nrel-bench]
* **On solar farms, the energy alone roughly breaks even with the tracker's cost.** Farm trackers stand in rows and backtrack to avoid shading each other, which cuts the Phoenix gain from 25% to about 19%. The extra energy is then worth about $0.10/W over 25 years ([`energy-yield/results/rows.csv`](energy-yield/results/rows.csv), at an assumed 35% ground cover). SEIA and Wood Mackenzie's like-for-like 2026 price for single axis tracking is $0.11/W more than fixed tilt.[^seia-q3] (Berkeley Lab's $0.01/W for 2025 projects compares different projects and does not control for size or location.[^lbl2026])
* **Yet 96% of new US utility solar capacity in 2025 used single axis trackers.**[^lbl2026] When a model disagrees with an industry, the model is probably missing something. The likeliest gap is timing: this model values every kWh the same, but trackers produce more in the morning and late afternoon, when power is worth more.[^lbl-value] Pricing every hour with 2025 California market data confirms it: in farm rows, trackers add 19% more energy but 34% more market revenue. Whether that makes them pay depends on how the farm is paid; see [part 6](energy-yield/README.md#6-value-not-energy-pricing-every-hour).
* **The controller barely changes energy, but it changes wear.** Even the worst light-sensor controller loses under 0.2% of a year's energy, while the unfiltered one moves the motors 12 times as often as a controller that calculates the sun's position.[^r-ctrl] Calculating the sun's position and confirming the panel angle with a tilt sensor (inclinometer) is how commercial trackers are described as pointing, partly because light sensors stop giving usable feedback when clouds cover the sun.[^fredericks]

Full results, assumptions and sources: [`energy-yield/README.md`](energy-yield/README.md).

| Part | Folder | What it does |
|---|---|---|
| Controller v1 | [`single-axis/`](single-axis) | One servo, two LDRs, manual sun slider |
| Controller v2 | [`dual-axis/`](dual-axis) | Pan and tilt servos, four LDRs, a real sun path, and a calculated sun position controller for comparison |
| Energy and economics | [`energy-yield/`](energy-yield) | pvlib model of a 4.8 kW system: flat, fixed, single and dual axis, two sites, payback, and controller cost |

```
solar-tracker-sim/
├── single-axis/
│   ├── wokwi/      sketch.ino, diagram.json, sun-sensor-head chip
│   └── tests/      native closed-loop test
├── dual-axis/
│   ├── wokwi/      sketch.ino, diagram.json, sun-sensor-head-2d chip
│   └── tests/      native closed-loop test (light sensors vs calculated sun position)
├── energy-yield/
│   ├── data/       NSRDB typical-year weather for Phoenix and Des Moines
│   ├── *.py        energy model, economics, controller cost, figures
│   ├── results/    CSV outputs
│   └── figures/    charts
├── common/         wokwi-api.h (used by the tests)
└── SOURCES.md      every reference in one list
```

# Part 1: The controller

The rest of this page covers the hardware-in-the-loop controller simulation. Part 2,
the energy and economics model, lives in [`energy-yield/`](energy-yield).

## How it works

The Arduino never sees the sun directly. It only sees the voltages from the
photoresistors. The custom chip sits between the Arduino and the world and closes
the loop:

```
        ┌──────────────── Sun + Sensor Head (custom chip) ────────────────┐
        │                                                                 │
 servo  │ decode pulse width ─► servo dynamics ─► panel angle             │
 PWM ──►│                                            │                    │
        │ sun position, lux ─► shading by divider wall                    │
        │ clouds, flicker ───► LDR response lag ─────┤                    │
        │                                            ▼                    │
        │                    lux ─► LDR resistance ─► voltage divider ───►├── LDR voltages
        └─────────────────────────────────────────────────────────────────┘     (A0, A1, ...)
                         ▲                                     │
                         │          Arduino Uno (sketch.ino)   ▼
                         └──── servo.write() ◄── control logic ◄── analogRead()
```

**Controller**, every 30 ms, for each axis:

1. Read the photoresistors through the Uno's 10-bit ADC, which maps 0 to 5 V onto 0 to 1023 (about 4.9 mV per step).[^arduino-adc]
2. `error = one side - the other side`
3. If `error > threshold`, step the servo 1° toward the brighter side. If `error < -threshold`, step 1° the other way. Otherwise hold.
4. With `USE_FILTER = true`, the error is first averaged over the last 20 readings and compared against a wider deadband.

The 30 ms loop, 1° step, threshold of 10 counts, 20-reading window and 40-count deadband are my design choices for this rebuild; the original values were not recorded.[^me]

**Plant model**, every 1 ms:

| Stage | Model | Basis |
|---|---|---|
| Servo input | Decodes the pulse width, 544 to 2400 µs → 0 to 180° | Arduino Servo library limits[^servo-lib] |
| Servo motion | Slew-rate limited at 600°/s | SG90 datasheet: 0.1 s per 60°[^sg90] |
| Optics | LDRs face the panel's direction with an opaque divider wall between them. Shaded fraction = 3 · tan(off-axis angle) | Assumption[^a-wall] |
| Diffuse light | 15% of the light reaches every sensor regardless of direction | Assumption[^a-diffuse] |
| Environment | Cloud cover: slow random process (τ = 3 s) shared by all sensors. Reflection flicker: independent per sensor (τ = 100 ms) | Assumption[^a-noise] |
| LDR response | First-order lag, 20 ms brightening and 50 ms darkening | Assumption, in the tens-of-milliseconds range CdS datasheets give[^a-ldr] |
| Electronics | R = 50 kΩ · (lux/10)^-0.7 in series with 10 kΩ | Wokwi's photoresistor module[^wokwi-ldr] |

## v1: Single axis

One servo turns the panel east and west. Two LDRs (east and west) sit on either
side of a divider wall. The chip has sliders for sun angle, brightness, cloud
cover, and reflection flicker, and draws a live view of the sun and panel.

### Results

From `single-axis/tests` (`make test`).[^r-single] The sun sweeps from -40° to +40° over 120 s.

| Scenario | Moves | Reversals | Mean pointing error |
|---|---|---|---|
| Clear, 400 lux, raw threshold | 117 | 1 | 1.1° |
| 30% cloud, 10% flicker, raw threshold | 2,014 | 468 | 1.9° |
| 30% cloud, 10% flicker, moving average + deadband | 147 | 3 | 2.3° |
| Clear, 400 lux, moving average + deadband | 127 | 1 | 5.1° |
| Clear, 10,000 lux, raw threshold | 102 | 1 | 6.1° |

* Under noisy light, the raw threshold reverses direction 468 times. The filter cuts that to 3, at the cost of about 0.4° more pointing error.[^r-single]
* On a clear day the deadband is wider than it needs to be (5.1° vs 1.1°), so the deadband should be tuned to the conditions.[^r-single]
* In bright light the tracking error grows (6.1° at 10,000 lux).[^r-single] With the module's 10 kΩ resistor, the output voltage falls toward 0 V in bright light (0.04 V at 100,000 lux in Wokwi's table),[^wokwi-ldr] so the ADC sees small differences between the sensors. A smaller fixed resistor or an optical filter would keep the signal in range outdoors.

**Sizing the deadband.** With the panel held on the sun, the error noise is:[^r-single]

| Conditions | Raw (1σ, counts) | 20-sample average (1σ, counts) |
|---|---|---|
| 30% cloud, 10% flicker | 18.3 | 10.9 |
| 50% cloud, 20% flicker | 38.1 | 22.8 |

A deadband of 40 counts is about 3.5σ of the averaged signal at 30% cloud (40 ÷ 10.9).
Averaging 20 samples reduces noise by about 1.7x (18.3 ÷ 10.9) rather than √20 ≈ 4.5x,
because the modeled flicker is correlated over about 100 ms[^a-noise] and consecutive
readings are only 30 ms apart.

## v2: Dual axis

A pan servo (pin 9) turns the panel east and west, and a tilt servo (pin 10) raises
it from the horizon to straight up. Four LDRs sit in quadrants separated by a
cross-shaped wall:[^a-wall]

```
   TOP_W | TOP_E
  -------+-------
   BOT_W | BOT_E
```

The sketch runs the same threshold logic as v1 on each axis independently:

* **Pan error** = (TOP_E + BOT_E) / 2 - (TOP_W + BOT_W) / 2
* **Tilt error** = (TOP_E + TOP_W) / 2 - (BOT_E + BOT_W) / 2

The chip calculates the light on each sensor in the panel's own frame: how far the
sun is off to the side shades one pair, and how far it is above or below shades the
other.

**Sun position.** With `dayLength = 0`, the sun follows the azimuth and elevation
sliders. Any other value runs a time lapse day of that many seconds along the sun
path for the chosen latitude and declination (season), using the standard elevation
formula sin(elevation) = sin δ sin φ + cos δ cos φ cos(hour angle).[^pvedu-elev] The
display shows a top view (azimuth) and a side view (elevation), with a line showing
the direction the panel faces.

### Results

From `dual-axis/tests` (`make test`).[^r-dual] One 120 s time lapse day at 45° latitude,
400 lux. Pointing error is the full 3D angle between the panel's facing direction and
the sun. Capture is the average of cos(error), the share of direct sunlight compared
with a perfectly aimed panel.[^pvedu-tilt]

| Scenario | Moves (pan / tilt) | Reversals (pan / tilt) | Mean error | 95th pct error | Capture |
|---|---|---|---|---|---|
| Equinox, clear, raw threshold | 248 / 111 | 1 / 2 | 1.6° | 2.0° | 100.0% |
| Equinox, 30% cloud, 10% flicker, raw | 1,525 / 1,441 | 355 / 394 | 2.2° | 3.9° | 99.9% |
| Equinox, 30% cloud, 10% flicker, filtered | 284 / 125 | 5 / 2 | 3.9° | 6.5° | 99.7% |
| Equinox, 30% cloud, 10% flicker, calculated sun position | 171 / 81 | 1 / 2 | 0.3° | 0.6° | 100.0% |
| Summer solstice, clear, raw | 1,330 / 173 | 1 / 3 | 6.0° | 22.1° | 98.0% |
| Winter solstice, clear, raw | 144 / 69 | 1 / 2 | 1.5° | 2.0° | 100.0% |

* The twitching problem shows up on both axes, and the filter fixes both (749 total reversals down to 7).[^r-dual]
* Pointing errors of a few degrees cost almost nothing in energy, because a panel's output follows the cosine of the angle between it and the sun,[^pvedu-tilt] and cos(4°) = 0.998. The real cost of twitching is servo wear and power, not lost sunlight. [`energy-yield/`](energy-yield) turns these errors into a year of lost energy: at most 0.17%.[^r-ctrl]
* **Calculated sun position** is the comparison case. Instead of reading the light sensors, the test computes where the sun is from the time of day, which is how commercial trackers are described as pointing,[^fredericks] and points there. Clouds can't fool it: 0.3° average error and 252 moves, against 2,966 moves for the raw light-sensor controller.[^r-dual]
* In summer the sun rises north of east: at 45°N on the June solstice, sunrise is at an azimuth of about 55° from north, compared with about 124° in December (calculated with NREL's Solar Position Algorithm through pvlib).[^spa] That puts the sunrise past the pan servo's range, so the panel waits at its limit, which is where the 22° worst case comes from.[^r-dual] The sketch also keeps commanding moves it can't make while pinned there, which inflates the pan move count.

## Running it in Wokwi

1. Create a new Arduino Uno project on wokwi.com.
2. Add a custom chip (**+ → Custom Chip**, language C) named `sun-sensor-head` for v1 or `sun-sensor-head-2d` for v2.[^wokwi-chips]
3. Copy the four files from that version's `wokwi/` folder into the matching tabs: `sketch.ino`, `diagram.json`, and the chip's `.chip.json` and `.chip.c`.
4. Press play. Use the chip's sliders to move the sun and add clouds or flicker. The Serial Monitor shows readings, servo angles, and reversal counts, and the Chips Console shows the chip's own view of the pointing error.

## Running the tests and the energy model

```
cd single-axis/tests && make test
cd dual-axis/tests && make test
cd energy-yield && pip install -r requirements.txt && python run_energy.py && python run_rows.py && python economics.py && python controller_energy.py && python make_figures.py
```

For the browser simulator's check against pvlib: `cd web-sim && node validate.js` (Node 18+).

Requires gcc or clang. `common/wokwi-api.h` is from [wokwi/inverter-chip](https://github.com/wokwi/inverter-chip) (MIT License, © 2022 Uri Shaked).

## Limitations

* Cloud and flicker statistics are assumptions, not measured data.[^a-noise]
* The servo model has no load, torque limit, or current draw, and the 5 V supply is ideal.
* The divider wall geometry is a design choice, not taken from the original hardware.[^a-wall]
* Sun brightness stays constant all day instead of changing with elevation and air mass.
* There is no night behavior: the tracker does not return east after sunset.

## Roadmap

* Value energy by the hour (time-of-use rates and wholesale prices) instead of a flat price.
* Shade the diffuse light between rows too (view factors), and put fixed tilt in rows for a like-for-like farm comparison.
* Drive the Wokwi chip's sun from real hourly NSRDB data instead of the built-in formulas and sliders.
* Return to the east at night and wait for sunrise.
* Stop commanding moves when a servo is already at its limit.
* Model the servos' electrical load and supply droop.

<!-- Footnotes. GitHub renders these as a numbered list at the bottom of the page. -->

[^me]: My own account of the 2023–2024 St. Olaf team project. The original code, logs and threshold values were not kept, so the rebuild's parameters are new design choices.
[^wokwi-uno]: Wokwi Docs, "Arduino Uno": the board "is powered by the ATmega328p chip" and "is simulated using the AVR8js Library." <https://docs.wokwi.com/parts/wokwi-arduino-uno>
[^wokwi-chips]: Wokwi Docs, "Chips API: Getting started" (custom chips written in C). <https://docs.wokwi.com/chips-api/getting-started>
[^wokwi-ldr]: Wokwi Docs, "wokwi-photoresistor-sensor": an LDR in series with a 10 kΩ resistor, defaults rl10 = 50 kΩ and gamma = 0.7, with AO falling from 4.96 V at 0.1 lux to 0.04 V at 100,000 lux. <https://docs.wokwi.com/parts/wokwi-photoresistor-sensor>. Gamma of 0.7 is also the typical value in the GL5528 photoresistor datasheet: <https://www.digikey.sg/htmldatasheets/production/2014143/0/0/1/gl5528.html>
[^arduino-adc]: Arduino, "analogRead()": on the Uno, a 10-bit ADC maps 0 to 5 V onto 0 to 1023, "0.0049 volts (4.9 mV) per unit." <https://docs.arduino.cc/language-reference/en/functions/analog-io/analogRead/>
[^servo-lib]: Arduino Servo library, `src/Servo.h`: `MIN_PULSE_WIDTH 544`, `MAX_PULSE_WIDTH 2400`, `REFRESH_INTERVAL 20000` µs. <https://github.com/arduino-libraries/Servo/blob/master/src/Servo.h>
[^sg90]: SG90 micro servo datasheet: "Operating speed: 0.1 s/60 degree." <https://bit.nkust.edu.tw/~csshieh/teach/111A/mc/datasheet/SG90.pdf>
[^a-wall]: Assumption. The model places an opaque wall between the sensors so that the sensor facing away from the sun is shaded when the panel is off target. The original prototype's sensor housing was not recorded, so the height-to-distance ratio of 3 is my choice; in this model it gives a clear signal within a few degrees of the sun.
[^a-diffuse]: Assumption, chosen near Phoenix's measured diffuse share of 23% of total sunlight ([`energy-yield/results/summary.csv`](energy-yield/results/summary.csv)) but rounded down for a simple sensor model.
[^a-noise]: Assumption. Cloud and reflection noise statistics were chosen to reproduce the twitching seen in the field, not fitted to measurements.
[^a-ldr]: Assumption. CdS photoresistors respond in tens of milliseconds; for example, the Advanced Photonix PDV-P9203 datasheet lists a 60 ms rise and 25 ms decay at 10 lux: <https://www.lasercomponents.com/fileadmin/user_upload/home/Datasheets/apx/ldr-cds/pdv-p9203-photoresistor.pdf>. The exact values used here (20 ms and 50 ms) are not taken from a specific part.
[^pvedu-tilt]: PVEducation, "Solar Radiation on a Tilted Surface": power "will always be at its maximum when the PV module is perpendicular to the sun," falling with the angle between them, and for a fixed tilt "the tilt angle is equal to the latitude of the location" gives the maximum over a year. <https://www.pveducation.org/es/pvcdrom/solar-radiation-tilted-surface>
[^pvedu-elev]: PVEducation, "Elevation Angle." <https://pveducation.org/pvcdrom/properties-of-sunlight/elevation-angle>
[^spa]: I. Reda and A. Andreas, "Solar position algorithm for solar radiation applications," *Solar Energy* 76(5), 577–589, 2004. <https://doi.org/10.1016/j.solener.2003.12.003>. NREL has since been renamed the National Laboratory of the Rockies (U.S. DOE, Dec. 1, 2025: <https://www.energy.gov/eere/articles/energy-department-renames-nrel-national-lab-rockies>).
[^pvlib]: K. S. Anderson, C. W. Hansen, W. F. Holmgren et al., "pvlib python: 2023 project update," *Journal of Open Source Software* 8(92), 5994, 2023. <https://doi.org/10.21105/joss.05994>
[^fredericks]: The Fredericks Company, "AN 1004: Inclinometers for Solar Tracking Systems": "The algorithm tells the system where to point," the inclinometer "confirms that the system is indeed pointing in the correct direction," and "when clouds obscure the sun, the photodiode may no longer provide usable position feedback." <https://www.frederickscompany.com/application-notes/inclinometers-for-solar-tracking-systems/>
[^es-trackers]: EnergySage, "Is a solar tracking system worth it?": systems with trackers "cost between 40 to 100 percent more" than without. <https://www.energysage.com/business-solutions/solar-trackers-everything-need-know/>
[^nrel-bench]: NREL, PV system cost benchmark for Q1 2024 (report 92257): residential modeled market price $3.15/W DC. <https://nrel.gov/docs/fy25osti/92257.pdf>
[^lbl2026]: Lawrence Berkeley National Laboratory, *Utility-Scale Solar, 2026 Edition* (slides, Oct. 2026): 96% of new capacity in 2025 used single-axis tracking (slide 25); installed cost $1.31/W DC tracking vs $1.30/W DC fixed-tilt for 2025 projects (slide 32). <https://eta-publications.lbl.gov/sites/default/files/2026-10/utility_scale_solar_2026_edition_slides.pdf>
[^r-summary]: This repository: [`energy-yield/results/summary.csv`](energy-yield/results/summary.csv), produced by [`energy-yield/run_energy.py`](energy-yield/run_energy.py).
[^r-econ]: This repository: [`energy-yield/results/economics.csv`](energy-yield/results/economics.csv), produced by [`energy-yield/economics.py`](energy-yield/economics.py). Discount rate, degradation and maintenance are assumptions listed in [`energy-yield/README.md`](energy-yield/README.md#2-economics).
[^r-ctrl]: This repository: [`energy-yield/results/controller_energy.csv`](energy-yield/results/controller_energy.csv), produced by [`energy-yield/controller_energy.py`](energy-yield/controller_energy.py) from the dual axis test and the pointing error curve.
[^r-single]: This repository: output of [`single-axis/tests/closed_loop_test.c`](single-axis/tests/closed_loop_test.c) (`make test`), which runs the v1 chip against a copy of the sketch's logic.
[^r-dual]: This repository: output of [`dual-axis/tests/closed_loop_test.c`](dual-axis/tests/closed_loop_test.c) (`make test`; `./closed_loop_test --csv` writes [`energy-yield/results/hil_dual_axis.csv`](energy-yield/results/hil_dual_axis.csv)).
[^seia-q3]: SEIA and Wood Mackenzie, *US Solar Market Insight Q3 2026*, executive summary, Sept. 2026: Q2 2026 modeled utility-scale prices of $0.95/W DC fixed-tilt and $1.06/W DC single-axis tracking. <https://tecsol-quotidien.fr/wp-content/uploads/2026/09/USSMI_Q3_2026_ES.pdf> (SOURCES.md #40)
[^lbl-value]: J. H. Kim, A. D. Mills, R. Wiser et al., "Project developer options to enhance the value of solar electricity as solar and storage penetrations increase," Berkeley Lab, Sept. 2021: tracking and similar options shift "solar production to higher-priced hours in the mornings and, especially, in late afternoons to evening." <https://emp.lbl.gov/news/project-developer-options-enhance-value-solar>
