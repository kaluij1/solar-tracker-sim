# Sources

Every claim in this repository and in its case study on my website is backed by one of three things:

1. **A published source** listed below.
2. **A result from this repository,** cited with the file that holds it (table at the bottom).
3. **An assumption,** labeled as one where it is used, with the reasoning.

Quoted phrases are taken directly from the source. NREL (the National Renewable Energy
Laboratory) was renamed the National Laboratory of the Rockies on December 1, 2025;[^n] the
documents below are cited under the name they were published with.

[^n]: U.S. Department of Energy, "Energy Department Renames NREL 'National Lab of the Rockies'," Dec. 1, 2025. <https://www.energy.gov/eere/articles/energy-department-renames-nrel-national-lab-rockies>

## Costs, prices and industry practice

| # | Source | What it supports |
|---|---|---|
| 1 | Lawrence Berkeley National Laboratory, *Utility-Scale Solar, 2026 Edition* (slides, Oct. 2026). <https://eta-publications.lbl.gov/sites/default/files/2026-10/utility_scale_solar_2026_edition_slides.pdf> | 96% of new US utility solar capacity in 2025 used single-axis tracking (slide 25); installed cost $1.31/W DC tracking vs $1.30/W DC fixed-tilt, 2025 projects (slide 32); PPA prices typically $25–35/MWh in CAISO and the non-ISO West; tracking adds "more than five percentage points" of capacity factor where sunlight is strongest; median O&M about $11/kW(AC)-yr (slide 36) |
| 2 | NREL, PV system cost benchmark, Q1 2024 (report 92257). <https://nrel.gov/docs/fy25osti/92257.pdf> | Residential (8 kW) modeled market price $3.15/W DC; tracking premium of $0.20/W DC from Berkeley Lab 2023 data |
| 3 | EnergySage, "Is a solar tracking system worth it?" <https://www.energysage.com/business-solutions/solar-trackers-everything-need-know/> | Trackers add "40 to 100 percent" to system cost; single axis gain "25 to 35 percent"; dual axis adds "five to 10 percent" more; trackers generally not worth it for residential, usually rooftop, systems |
| 4 | EnergySage, "Cost of electricity in Arizona." <https://www.energysage.com/local-data/electricity-cost/az/> | Average Arizona residential rate of 15 cents/kWh, November 2026, from customer bills |
| 5 | J. H. Kim, A. D. Mills, R. Wiser et al., "Project developer options to enhance the value of solar electricity as solar and storage penetrations increase," Berkeley Lab, Sept. 2021. <https://emp.lbl.gov/news/project-developer-options-enhance-value-solar> | Tracking shifts "solar production to higher-priced hours in the mornings and, especially, in late afternoons to evening" |
| 6 | The Fredericks Company, "AN 1004: Inclinometers for Solar Tracking Systems." <https://www.frederickscompany.com/application-notes/inclinometers-for-solar-tracking-systems/> | Trackers point using an algorithm ("The algorithm tells the system where to point") and confirm with an inclinometer; photodiodes may give no "usable position feedback" under clouds |
| 7 | K. Anderson and M. Mikofski, "Slope-Aware Backtracking for Single-Axis Trackers," NREL/TP-5K00-76626, 2020. <https://doi.org/10.2172/1660126> | What backtracking is, and that it gives up some direct sunlight to avoid row-to-row shading |
| 34 | S. Chunduri, "Dual-Axis Trackers Remain A Niche In Utility Applications," TaiyangNews, Apr. 2, 2026. <https://taiyangnews.info/technology/dual-axis-trackers-remain-a-niche-in-utility-applications> | Dual axis trackers are "not well accepted in commercial utility-scale deployments" because of "complex mechanical architecture and heavy structural requirements" (cited on the case study page) |

## Solar physics and modeling methods

| # | Source | What it supports |
|---|---|---|
| 8 | K. S. Anderson, C. W. Hansen, W. F. Holmgren et al., "pvlib python: 2023 project update," *JOSS* 8(92), 5994, 2023. <https://doi.org/10.21105/joss.05994> | The modeling library (version 0.16.1) |
| 9 | I. Reda and A. Andreas, "Solar position algorithm for solar radiation applications," *Solar Energy* 76(5), 577–589, 2004. <https://doi.org/10.1016/j.solener.2003.12.003> | Sun position every hour; solstice sunrise directions |
| 10 | R. Perez, P. Ineichen, R. Seals, J. Michalsky and R. Stewart, "Modeling daylight availability and irradiance components from direct and global irradiance," *Solar Energy* 44(5), 271–289, 1990. <https://archive-ouverte.unige.ch/unige:17206> | Light on a tilted panel (Perez sky model) |
| 11 | W. De Soto, S. A. Klein and W. A. Beckman, "Improvement and validation of a model for photovoltaic array performance," *Solar Energy* 80, 78–88, 2006. <https://doi.org/10.1016/j.solener.2005.06.010> | Glass reflection model; single diode model |
| 12 | B. Marion, "Numerical method for angle-of-incidence correction factors for diffuse radiation incident photovoltaic modules," *Solar Energy* 147, 344–348, 2017. <https://doi.org/10.1016/j.solener.2017.03.027> | Reflection of diffuse light |
| 13 | D. L. King, W. E. Boyson and J. A. Kratochvil, "Photovoltaic Array Performance Model," SAND2004-3535, 2004. <https://www.osti.gov/biblio/919131> | Cell temperature model |
| 14 | A. Dobos, "An Improved Coefficient Calculator for the California Energy Commission 6 Parameter Photovoltaic Module Model," *J. Solar Energy Engineering* 134, 2012. <https://doi.org/10.1115/1.4005759> | CEC module model |
| 15 | D. King, S. Gonzalez, G. Galbraith and W. Boyson, "Performance Model for Grid-Connected Photovoltaic Inverters," SAND2007-5036, 2007. <https://doi.org/10.2172/920449> | Inverter efficiency and clipping |
| 16 | A. P. Dobos, "PVWatts Version 5 Manual," NREL/TP-6A20-62641, 2014. <https://doi.org/10.2172/1158421> | Default system losses (14.08%); PVWatts cross-check equations |
| 17 | California Energy Commission module and inverter databases, as distributed with NREL's System Advisor Model and loaded by `pvlib.pvsystem.retrieve_sam`. <https://github.com/NREL/SAM> | Module and inverter specifications |
| 18 | PVEducation, "Solar Radiation on a Tilted Surface." <https://www.pveducation.org/es/pvcdrom/solar-radiation-tilted-surface> | Output is greatest when the panel is perpendicular to the sun; a fixed tilt equal to the latitude maximizes yearly output |
| 19 | PVEducation, "Elevation Angle." <https://pveducation.org/pvcdrom/properties-of-sunlight/elevation-angle> | Sun elevation formula used in the Wokwi chip |
| 20 | Penn State, EME 812, "3.1. Why tracking?" <https://courses.ems.psu.edu/eme812/node/519> | Trackers hold the best angle to the sun; flat panels "accept both beam and diffuse radiation" |

## Weather data

| # | Source | What it supports |
|---|---|---|
| 21 | M. Sengupta, Y. Xie, A. Lopez, A. Habte, G. Maclaurin and J. Shelby, "The National Solar Radiation Data Base (NSRDB)," *Renewable and Sustainable Energy Reviews* 89, 51–60, 2018. <https://doi.org/10.1016/j.rser.2018.03.003> | Source of all weather files |
| 22 | S. Wilcox and W. Marion, *Users Manual for TMY3 Data Sets*, NREL/TP-581-43156, 2008. <https://www.nrel.gov/docs/fy08osti/43156.pdf> | How typical years are built; "not suited for designing systems to meet the worst-case conditions" |
| 23 | M. Sengupta and A. Habte, NREL/CP-5D00-74768, 2019. <https://nrel.gov/docs/fy20osti/74768.pdf> | A typical DNI year (TDY) weights direct sunlight 100% |
| 24 | NREL System Advisor Model, sample weather files. <https://github.com/NREL/SAM> | Des Moines and older Phoenix files |

## Hardware and simulation tools

| # | Source | What it supports |
|---|---|---|
| 25 | Wokwi Docs, "Arduino Uno." <https://docs.wokwi.com/parts/wokwi-arduino-uno> | The Uno "is powered by the ATmega328p chip" and "is simulated using the AVR8js Library" |
| 26 | Wokwi Docs, "Chips API: Getting started." <https://docs.wokwi.com/chips-api/getting-started> | Custom chips written in C |
| 27 | Wokwi Docs, "wokwi-photoresistor-sensor." <https://docs.wokwi.com/parts/wokwi-photoresistor-sensor> | LDR in series with 10 kΩ; rl10 = 50 kΩ, gamma = 0.7; AO from 4.96 V (0.1 lux) to 0.04 V (100,000 lux) |
| 28 | GL5528 photoresistor datasheet (Seeed). <https://www.digikey.sg/htmldatasheets/production/2014143/0/0/1/gl5528.html> | Typical gamma of 0.7 for a common CdS photoresistor |
| 29 | Advanced Photonix PDV-P9203 CdS photoresistor datasheet. <https://www.lasercomponents.com/fileadmin/user_upload/home/Datasheets/apx/ldr-cds/pdv-p9203-photoresistor.pdf> | CdS response times in the tens of milliseconds (60 ms rise, 25 ms decay at 10 lux) |
| 30 | Arduino, "analogRead()." <https://docs.arduino.cc/language-reference/en/functions/analog-io/analogRead/> | 10-bit ADC, 0 to 1023, 4.9 mV per step on the Uno |
| 31 | Arduino Servo library, `src/Servo.h`. <https://github.com/arduino-libraries/Servo/blob/master/src/Servo.h> | Pulse widths 544 to 2400 µs; 20 ms refresh |
| 32 | SG90 micro servo datasheet. <https://bit.nkust.edu.tw/~csshieh/teach/111A/mc/datasheet/SG90.pdf> | "Operating speed: 0.1 s/60 degree" |
| 33 | wokwi/inverter-chip (MIT License). <https://github.com/wokwi/inverter-chip> | `common/wokwi-api.h` |

## Results from this repository

| Claim | File | Produced by |
|---|---|---|
| Energy, gains, capacity factor, diffuse share, PVWatts cross-check | [`energy-yield/results/summary.csv`](energy-yield/results/summary.csv) | `energy-yield/run_energy.py` |
| Monthly energy | [`energy-yield/results/monthly.csv`](energy-yield/results/monthly.csv) | `energy-yield/run_energy.py` |
| Best tilt and the tilt curve | [`energy-yield/results/tilt_sweep.csv`](energy-yield/results/tilt_sweep.csv) | `energy-yield/run_energy.py` |
| Results across weather data versions | [`energy-yield/results/dataset_check.csv`](energy-yield/results/dataset_check.csv) | `energy-yield/run_energy.py` |
| Energy lost vs pointing error | [`energy-yield/results/pointing_error.csv`](energy-yield/results/pointing_error.csv) | `energy-yield/run_energy.py` |
| Break-even premiums and payback | [`energy-yield/results/economics.csv`](energy-yield/results/economics.csv) | `energy-yield/economics.py` |
| Controller pointing error, moves, reversals, energy cost | [`energy-yield/results/controller_energy.csv`](energy-yield/results/controller_energy.csv), [`energy-yield/results/hil_dual_axis.csv`](energy-yield/results/hil_dual_axis.csv) | `dual-axis/tests` (`--csv`), `energy-yield/controller_energy.py` |
| Single axis controller results and noise | Output of `make test` | `single-axis/tests/closed_loop_test.c` |
| Dual axis controller results | Output of `make test` | `dual-axis/tests/closed_loop_test.c` |

## Personal account

The story of the original prototype (team of five, St. Olaf, 2023–2024, twitching
outdoors, the moving average and deadband fix) is my own account. The original code,
logs and parameter values were not kept.
