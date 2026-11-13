# Solar Tracker Simulation (v1: single axis)

A hardware-in-the-loop simulation of a light-seeking solar tracker. Real Arduino
firmware runs on an emulated ATmega328 in [Wokwi](https://wokwi.com), and a custom
simulated chip models the physical world around it: the sun, the servo, the
photoresistors, clouds, and reflections.

This rebuilds the control system from a dual axis solar tracker I worked on with a
team of five at St. Olaf. The original field logs were lost, so this project
recreates the problem we hit outdoors (servo twitching caused by sensor noise) and
the fix (moving average plus a noise-sized deadband) in a setting where every
variable can be measured.

## How it works

```
        ┌──────────────── Sun + Sensor Head (custom chip) ────────────────┐
        │                                                                 │
 PWM ──►│ decode pulse width ─► servo dynamics ─► panel angle             │
 (pin 9)│                                            │                    │
        │ sun angle, lux ──► shading by divider wall ┤                    │
        │ clouds, flicker ─► LDR response lag ───────┤                    │
        │                                            ▼                    │
        │                    lux ─► LDR resistance ─► voltage divider ───►├── EAST (A0)
        │                                                                 ├── WEST (A1)
        └─────────────────────────────────────────────────────────────────┘
                         ▲                                     │
                         │          Arduino Uno (sketch.ino)   ▼
                         └──── servo.write() ◄── control logic ◄── analogRead()
```

**Controller (`wokwi/sketch.ino`)**, every 30 ms:

1. Read both photoresistors through the 10-bit ADC (0 to 1023).
2. `error = east - west`
3. If `error > threshold`, step the servo 1° east. If `error < -threshold`, step 1° west. Otherwise hold.
4. With `USE_FILTER = true`, the error is first averaged over the last 20 readings and compared against a wider deadband.

**Plant model (`wokwi/sun-sensor-head.chip.c`)**, every 1 ms:

| Stage | Model |
|---|---|
| Servo input | Decodes the Arduino Servo library pulse width (544 to 2400 µs → 0 to 180°) |
| Servo motion | Slew-rate limited at 600°/s (SG90 class, about 0.1 s per 60°) |
| Optics | Both LDRs face the panel normal with an opaque divider wall between them. Shaded fraction = 3 · tan(off-axis angle). 15% diffuse sky light reaches both |
| Environment | Cloud cover: slow random process (τ = 3 s) shared by both sensors. Reflection flicker: independent per sensor (τ = 100 ms) |
| LDR response | First-order lag, 20 ms brightening and 50 ms darkening |
| Electronics | R = 50 kΩ · (lux/10)^-0.7 in series with 10 kΩ, matching Wokwi's photoresistor module |

The chip also draws a small live view of the sun, the panel, and how brightly each LDR is lit.

## Running it in Wokwi

1. Create a new Arduino Uno project on wokwi.com.
2. Add a custom chip (**+ → Custom Chip**) named `sun-sensor-head`, language C.
3. Copy the four files from `wokwi/` into the matching tabs: `sketch.ino`, `diagram.json`, `sun-sensor-head.chip.json`, `sun-sensor-head.chip.c`.
4. Press play. Use the chip's sliders to move the sun and add clouds or flicker. The Serial Monitor (or Serial Plotter) shows readings, servo angle, moves, and reversals.

## Results

From `tests/closed_loop_test.c`, which runs the chip natively against a copy of the
sketch's logic. The sun sweeps from -40° to +40° over 120 s.

| Scenario | Moves | Reversals | Mean pointing error |
|---|---|---|---|
| Clear, 400 lux, raw threshold | 117 | 1 | 1.1° |
| 30% cloud, 10% flicker, raw threshold | 2,014 | 468 | 1.9° |
| 30% cloud, 10% flicker, moving average + deadband | 147 | 3 | 2.3° |
| Clear, 400 lux, moving average + deadband | 127 | 1 | 5.1° |
| Clear, 10,000 lux, raw threshold | 102 | 1 | 6.1° |

**What this shows**

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

## Running the tests

```
cd tests
make test
```

Requires gcc or clang. `tests/wokwi-api.h` is from [wokwi/inverter-chip](https://github.com/wokwi/inverter-chip) (MIT License, © 2022 Uri Shaked).

## Limitations

* Single axis only.
* Cloud and flicker statistics are assumptions, not measured data.
* The servo model has no load, torque limit, or current draw, and the 5 V supply is ideal.
* The divider wall geometry (height to distance ratio of 3) is a design choice, not taken from the original hardware.

## Roadmap

* **v2:** dual axis, with four LDRs, two servos, and a sun path that moves in both azimuth and elevation.
* Drive the sun from real solar position data (pvlib) and measured irradiance (NREL) instead of sliders.
* Model the servo's electrical load and supply droop.
