"""Is the extra energy from tracking worth the extra cost?

Instead of guessing one tracker price, this asks a sturdier question:
**how much extra could a tracker cost (per watt) and still pay for itself over the
system's life?** That "break-even premium" is then compared with real market premiums.

    break-even premium ($/W) = present value of 25 years of
                               (extra kWh x electricity value - extra maintenance)

Run run_energy.py first. Writes results/economics.csv.
"""
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
RES = HERE / "results"

LIFE_YEARS = 25
DISCOUNT_RATE = 0.06          # assumption: real discount rate
DEGRADATION = 0.005           # assumption: panels lose 0.5% of output per year

# Each market has its own price of electricity, base system cost and tracker premium.
MARKETS = {
    "Residential": {
        "energy_value": 0.15,             # $/kWh avoided retail price, Arizona
        "energy_value_src": "EnergySage, average Arizona residential rate, Nov 2026",
        "base_cost": 3.15,                # $/W DC, fixed system
        "base_cost_src": "NREL Q1 2024 PV cost benchmark, residential modeled market price",
        "extra_om": 20.0,                 # $/kW DC per year, assumption (about $100/yr for 4.8 kW)
        "premium_low": 0.40, "premium_high": 1.00,   # tracker adds 40-100% to system cost
        "premium_src": "EnergySage: systems with trackers cost 40 to 100% more",
    },
    "Utility scale": {
        "energy_value": 0.030,            # $/kWh = $30/MWh power purchase agreement price
        "energy_value_src": "LBNL Utility-Scale Solar 2026: PPAs typically $25-35/MWh in CAISO and the non-ISO West",
        "base_cost": 1.30,                # $/W DC, fixed-tilt projects, 2025
        "base_cost_src": "LBNL Utility-Scale Solar 2026, installed cost by racking, 2025 projects",
        "extra_om": 2.0,                  # $/kW DC per year, assumption
        "premium_low": 0.01 / 1.30, "premium_high": 0.20 / 1.30,   # $0.01/W (2025) to $0.20/W (2023)
        "premium_src": "LBNL: tracking $1.31/W DC vs fixed $1.30/W DC in 2025; $0.20/W DC premium in 2023 data (via NREL Q1 2024 benchmark)",
    },
}


def present_value_factor(rate=DISCOUNT_RATE, years=LIFE_YEARS, degradation=DEGRADATION):
    """Sum over the system life of (1 - degradation)^t / (1 + rate)^t."""
    return sum((1 - degradation) ** t / (1 + rate) ** (t + 1) for t in range(years))


def run():
    summary = pd.read_csv(RES / "summary.csv")
    pvf = present_value_factor()
    rows = []
    for site, s in summary.groupby("site"):
        s = s.set_index("setup")
        fixed_yield = s.loc["Fixed, best tilt", "Specific yield (kWh/kWp)"]
        for market, m in MARKETS.items():
            for setup in ["Single axis", "Dual axis"]:
                extra_kwh = s.loc[setup, "Specific yield (kWh/kWp)"] - fixed_yield      # per kW DC per year
                yearly_value = extra_kwh * m["energy_value"] - m["extra_om"]            # $ per kW DC per year
                breakeven = pvf * yearly_value / 1000                                   # $ per W DC
                prem_low = m["premium_low"] * m["base_cost"]
                prem_high = m["premium_high"] * m["base_cost"]
                payback_low = prem_low * 1000 / yearly_value if yearly_value > 0 else float("inf")
                payback_high = prem_high * 1000 / yearly_value if yearly_value > 0 else float("inf")
                if prem_high <= breakeven:
                    verdict = "Pays off"
                elif prem_low <= breakeven:
                    verdict = "Pays off only if cheap"
                else:
                    verdict = "Does not pay off"
                if market == "Utility scale" and setup == "Dual axis":
                    verdict = "No market price data"
                rows.append({
                    "site": site, "market": market, "setup": setup,
                    "extra_kwh_per_kw": extra_kwh, "gain_pct": 100 * extra_kwh / fixed_yield,
                    "value_per_kwh": m["energy_value"], "yearly_value_per_kw": yearly_value,
                    "breakeven_premium_per_w": breakeven,
                    "market_premium_low_per_w": prem_low, "market_premium_high_per_w": prem_high,
                    "simple_payback_low_yr": payback_low, "simple_payback_high_yr": payback_high,
                    "verdict": verdict,
                })
    out = pd.DataFrame(rows)
    out.to_csv(RES / "economics.csv", index=False)

    # How the break-even premium moves with the price of electricity (Phoenix, single axis)
    s = summary[summary.site == "Phoenix, AZ"].set_index("setup")
    extra = s.loc["Single axis", "Specific yield (kWh/kWp)"] - s.loc["Fixed, best tilt", "Specific yield (kWh/kWp)"]
    sens = pd.DataFrame({"energy_value_per_kwh": [x / 1000 for x in range(10, 201, 5)]})
    for market, m in MARKETS.items():
        sens[market] = pvf * (extra * sens["energy_value_per_kwh"] - m["extra_om"]) / 1000
    sens.to_csv(RES / "breakeven_vs_price.csv", index=False)
    return out, pvf


if __name__ == "__main__":
    out, pvf = run()
    pd.set_option("display.width", 220)
    print(f"Present value factor: {pvf:.2f} (25 years, {DISCOUNT_RATE:.0%} discount, {DEGRADATION:.1%}/yr degradation)\n")
    print(out.round(3).to_string(index=False))
    print("\nAssumptions and sources:")
    for market, m in MARKETS.items():
        print(f"  {market}: value {m['energy_value_src']}; base cost {m['base_cost_src']}; premium {m['premium_src']}")
