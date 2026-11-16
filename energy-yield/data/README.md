# Weather data

All files are hourly typical-year weather from NREL's National Solar Radiation Database (NSRDB).

| File | Source |
|---|---|
| `nsrdb/phoenix_tmy-2022.csv` to `phoenix_tmy-2025.csv` | NSRDB typical meteorological year, versions 2022 to 2025, downloaded from the NSRDB Viewer (location 33.49, -112.06). Timestamps in UTC |
| `nsrdb/phoenix_tdy-2023.csv` to `phoenix_tdy-2025.csv` | NSRDB typical direct normal year (months chosen mainly for direct sunlight), same location |
| `phoenix_az_33.450495_-111.983688_psmv3_60_tmy.csv` | NSRDB PSM v3 TMY, from the sample weather files in [NREL SAM](https://github.com/NREL/SAM) |
| `des_moines_ia_41.586835_-93.624959_psmv3_60_tmy.csv` | NSRDB PSM v3 TMY, from the sample weather files in NREL SAM |

Columns used by the model: GHI, DNI and DHI (sunlight, W/m²), air temperature, wind speed,
pressure and surface albedo.
