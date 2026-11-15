# Solar Tracker Simulation

A hardware-in-the-loop simulation of a light-seeking solar tracker. Real Arduino
firmware runs on an emulated ATmega328 in [Wokwi](https://wokwi.com), and a custom
simulated chip models the physical world around it: the sun, the servos, the
photoresistors, clouds, and reflections.

This rebuilds the control system from a dual axis solar tracker I worked on with a
team of five at St. Olaf. The original field logs were lost, so this project
recreates the problem we hit outdoors (servo twitching caused by sensor noise) and
the fix (moving average plus a noise-sized deadband) in a setting where every
variable can be measured.

| Version | Folder | What it adds |
|---|---|---|
| v1 | [`single-axis/`](single-axis) | One servo, two LDRs, manual sun slider |
| v2 | [`dual-axis/`](dual-axis) | Pan and tilt servos, four LDRs, a real sun path by latitude and season |

```
solar-tracker-sim/
├── single-axis/
│   ├── wokwi/      sketch.ino, diagram.json, sun-sensor-head chip
│   └── tests/      native closed-loop test
├── dual-axis/
│   ├── wokwi/      sketch.ino, diagram.json, sun-sensor-head-2d chip
│   └── tests/      native closed-loop test
└── common/         wokwi-api.h (used by the tests)
```

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

1. Read the photoresistors through the 10-bit ADC (0 to 1023).
2. `error = one side - the other side`
3. If `error > threshold`, step the servo 1° toward the brighter side. If `error < -threshold`, step 1° the other way. Otherwise hold.
4. With `USE_FILTER = true`, the error is first averaged over the last 20 readings and compared against a wider deadband.

**Plant model**, every 1 ms:

| Stage | Model |
|---|---|
| Servo input | Decodes the Arduino Servo library pulse width (544 to 2400 µs → 0 to 180°) |
| Servo motion | Slew-rate limited at 600°/s (SG90 class, about 0.1 s per 60°) |
| Optics | LDRs face the panel's direction with an opaque divider wall between them. Shaded fraction = 3 · tan(off-axis angle). 15% diffuse sky light reaches every sensor |
| Environment | Cloud cover: slow random process (τ = 3 s) shared by all sensors. Reflection flicker: independent per sensor (τ = 100 ms) |
| LDR response | First-order lag, 20 ms brightening and 50 ms darkening |
| Electronics | R = 50 kΩ · (lux/10)^-0.7 in series with 10 kΩ, matching Wokwi's photoresistor module |

## v1: Single axis

One servo turns the panel east and west. Two LDRs (east and west) sit on either
side of a divider wall. The chip has sliders for sun angle, brightness, cloud
cover, and reflection flicker, and draws a live view of the sun and panel.

### Results

From `single-axis/tests`. The sun sweeps from -40° to +40° over 120 s.

| Scenario | Moves | Reversals | Mean pointing error |
|---|---|---|---|
| Clear, 400 lux, raw threshold | 117 | 1 | 1.1° |
| 30% cloud, 10% flicker, raw threshold | 2,014 | 468 | 1.9° |
| 30% cloud, 10% flicker, moving average + deadband | 147 | 3 | 2.3° |
| Clear, 400 lux, moving average + deadband | 127 | 1 | 5.1° |
| Clear, 10,000 lux, raw threshold | 102 | 1 | 6.1° |

* Under noisy light, the raw threshold reverses direction 468 times. The filter cuts that to 3, at the cost of about 0.4° more pointing error.
* On a clear day the deadband is wider than it needs to be (5.1° vs 1.1°). The deadband should be tuned to the conditions.
* In bright sun the LDR's resistance drops so low that the divider output sits near 0 V and the ADC loses resolution. The module's 10 kΩ resistor suits indoor light. Outdoors it would need a smaller resistor or an optical filter.

**Sizing the deadband.** With the panel held on the sun, the error noise is:

| Conditions | Raw (1σ, counts) | 20-sample average (1σ, counts) |
|---|---|---|
| 30% cloud, 10% flicker | 18.3 | 10.9 |
| 50% cloud, 20% flicker | 38.1 | 22.8 |

A deadband of 40 counts is about 3.5σ of the averaged signal at 30% cloud. Averaging
20 samples reduces noise by about 1.7x rather than √20 ≈ 4.5x, because the flicker is
correlated over about 100 ms and consecutive readings are 30 ms apart.

## v2: Dual axis

A pan servo (pin 9) turns the panel east and west, and a tilt servo (pin 10) raises
it from the horizon to straight up. Four LDRs sit in quadrants separated by a
cross-shaped wall:

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
sliders. Any other value runs a time lapse day of that many seconds along the real
sun path for the chosen latitude and declination (season), from the standard
spherical astronomy formulas. The display shows a top view (azimuth) and a side view
(elevation), with a line showing the direction the panel faces.

### Results

From `dual-axis/tests`. One 120 s time lapse day at 45° latitude (about Minneapolis),
400 lux. Pointing error is the full 3D angle between the panel's facing direction and
the sun. Capture is the average of cos(error), the share of direct sunlight compared
with a perfectly aimed panel.

| Scenario | Moves (pan / tilt) | Reversals (pan / tilt) | Mean error | 95th pct error | Capture |
|---|---|---|---|---|---|
| Equinox, clear, raw threshold | 248 / 111 | 1 / 2 | 1.6° | 2.0° | 100.0% |
| Equinox, 30% cloud, 10% flicker, raw | 1,525 / 1,441 | 355 / 394 | 2.2° | 3.9° | 99.9% |
| Equinox, 30% cloud, 10% flicker, filtered | 284 / 125 | 5 / 2 | 3.9° | 6.5° | 99.7% |
| Summer solstice, clear, raw | 1,330 / 173 | 1 / 3 | 6.0° | 22.1° | 98.0% |
| Winter solstice, clear, raw | 144 / 69 | 1 / 2 | 1.5° | 2.0° | 100.0% |

* The twitching problem shows up on both axes, and the filter fixes both (749 total reversals down to 7).
* Pointing errors of a few degrees cost almost nothing in energy, because cos(4°) is still 99.8%. The real cost of twitching is servo wear and power, not lost sunlight.
* In summer the sun rises north of east, past the pan servo's 180° limit. The panel sits at its limit until the sun comes back into range, which is where the 22° worst case comes from. The sketch also keeps commanding moves it can't make while pinned there, which inflates the pan move count.

## Running it in Wokwi

1. Create a new Arduino Uno project on wokwi.com.
2. Add a custom chip (**+ → Custom Chip**, language C) named `sun-sensor-head` for v1 or `sun-sensor-head-2d` for v2.
3. Copy the four files from that version's `wokwi/` folder into the matching tabs: `sketch.ino`, `diagram.json`, and the chip's `.chip.json` and `.chip.c`.
4. Press play. Use the chip's sliders to move the sun and add clouds or flicker. The Serial Monitor shows readings, servo angles, and reversal counts, and the Chips Console shows the chip's own view of the pointing error.

## Running the tests

```
cd single-axis/tests && make test
cd dual-axis/tests && make test
```

Requires gcc or clang. `common/wokwi-api.h` is from [wokwi/inverter-chip](https://github.com/wokwi/inverter-chip) (MIT License, © 2022 Uri Shaked).

## Limitations

* Cloud and flicker statistics are assumptions, not measured data.
* The servo model has no load, torque limit, or current draw, and the 5 V supply is ideal.
* The divider wall geometry (height to distance ratio of 3) is a design choice, not taken from the original hardware.
* Sun brightness stays constant all day instead of changing with elevation and air mass.
* There is no night behavior: the tracker does not return east after sunset.

## Roadmap

* Drive the sun from real solar position data (pvlib) and measured irradiance (NREL) instead of the built-in formulas and sliders.
* Return to the east at night and wait for sunrise.
* Stop commanding moves when a servo is already at its limit.
* Model the servos' electrical load and supply droop.
