"""Charts for the energy and economics results.
Run run_energy.py, economics.py and controller_energy.py first."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
RES = HERE / "results"
FIG = HERE / "figures"
FIG.mkdir(exist_ok=True)
for old in FIG.glob("*.png"):
    old.unlink()

SURFACE, INK, INK2, GRID, NEUTRAL = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df", "#c3c2b7"
SETUPS = ["Flat", "Fixed, best tilt", "Single axis", "Dual axis"]
COLOR = dict(zip(SETUPS, ["#eda100", "#2a78d6", "#eb6834", "#1baf7a"]))   # fixed order, never cycled
SITES = ["Phoenix, AZ", "Des Moines, IA"]

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "text.color": INK, "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "bold",
    "axes.titlelocation": "left", "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
    "legend.frameon": False, "lines.linewidth": 2,
})


def save(fig, name, rect=None):
    fig.tight_layout(rect=rect)
    fig.savefig(FIG / name, dpi=160)
    plt.close(fig)


summary = pd.read_csv(RES / "summary.csv")
monthly = pd.read_csv(RES / "monthly.csv", header=[0, 1], index_col=0)
daily = pd.read_csv(RES / "daily_profiles.csv", header=[0, 1, 2], index_col=0)
waterfall = pd.read_csv(RES / "waterfall.csv", header=[0, 1], index_col=0)
sweep = pd.read_csv(RES / "tilt_sweep.csv", index_col=0)
econ = pd.read_csv(RES / "economics.csv")
pointing = pd.read_csv(RES / "pointing_error.csv")
controllers = pd.read_csv(RES / "controller_energy.csv")

# 1. energy per kW installed, by site and setup ------------------------------------
fig, ax = plt.subplots(figsize=(8.5, 4.2))
width, gap = 0.19, 0.02
for i, setup in enumerate(SETUPS):
    vals = [summary[(summary.site == s) & (summary.setup == setup)]["Specific yield (kWh/kWp)"].iloc[0] for s in SITES]
    x = np.arange(len(SITES)) + (i - 1.5) * (width + gap)
    ax.bar(x, vals, width, color=COLOR[setup], label=setup)
    for xi, v, s in zip(x, vals, SITES):
        gain = summary[(summary.site == s) & (summary.setup == setup)]["Gain vs fixed (%)"].iloc[0]
        label = f"{v:,.0f}" if setup != "Single axis" and setup != "Dual axis" else f"{v:,.0f}\n+{gain:.0f}%"
        ax.text(xi, v + 30, label, ha="center", va="bottom", fontsize=8, color=INK2)
ax.set_xticks(range(len(SITES)))
ax.set_xticklabels(SITES)
ax.set_ylabel("kWh per kW installed, per year")
ax.set_ylim(0, 2900)
ax.set_title("Yearly energy per kW of panels (gains shown vs fixed tilt)")
ax.legend(loc="lower center", ncol=4, bbox_to_anchor=(0.5, -0.25))
save(fig, "yield_by_site.png")

# 2. monthly energy, Phoenix -----------------------------------------------------------
for site, fname in [("Phoenix, AZ", "monthly_phoenix.png"), ("Des Moines, IA", "monthly_des_moines.png")]:
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    for setup in SETUPS:
        ax.plot(monthly.index, monthly[(site, setup)], color=COLOR[setup], marker="o", markersize=5, label=setup)
    ax.set_title(f"Monthly AC energy, 4.8 kW system, {site}")
    ax.set_ylabel("kWh per month")
    ax.set_ylim(0, None)
    ax.legend(loc="lower center", ncol=4, bbox_to_anchor=(0.5, -0.3))
    save(fig, fname)

# 3. a summer and a winter day, Phoenix --------------------------------------------------
fig, axes = plt.subplots(1, 2, figsize=(10, 4.3), sharey=True)
for ax, day, label in zip(axes, ["2023-06-21", "2023-12-21"], ["June 21", "December 21"]):
    for setup in SETUPS:
        p = daily[("Phoenix, AZ", setup, day)]
        ax.plot(p.index + 0.5, p.values, color=COLOR[setup], label=setup)
    ax.axhline(3.85, color=INK2, linewidth=1, linestyle=(0, (4, 3)))
    ax.text(5.2, 4.02, "inverter limit 3.85 kW", color=INK2, fontsize=8)
    ax.set_title(f"Phoenix, {label}")
    ax.set_xlim(5, 20)
    ax.set_xlabel("Hour of day")
axes[0].set_ylabel("AC power (kW)")
axes[0].set_ylim(0, 4.4)
fig.legend(*axes[0].get_legend_handles_labels(), loc="lower center", ncol=4, bbox_to_anchor=(0.5, 0))
save(fig, "daily_profiles_phoenix.png", rect=(0, 0.08, 1, 1))

# 4. where the energy goes, Phoenix fixed --------------------------------------------------
values = waterfall[("Phoenix, AZ", "Fixed, best tilt")].values
steps = ["Light on panel\nx nameplate", "Glass\nreflection", "Heat and\nlow light", "System\nlosses", "Inverter", "AC output"]
fig, ax = plt.subplots(figsize=(8.5, 4))
ax.bar(0, values[0], color=COLOR["Fixed, best tilt"], width=0.6)
for i in range(1, len(values)):
    drop = values[i - 1] - values[i]
    ax.bar(i, drop, bottom=values[i], color=NEUTRAL, width=0.6)
    ax.text(i, values[i - 1] + 150, f"-{drop:,.0f}\n({100*drop/values[0]:.1f}%)", ha="center", fontsize=8, color=INK2)
ax.bar(len(values), values[-1], color=COLOR["Fixed, best tilt"], width=0.6)
ax.text(0, values[0] + 150, f"{values[0]:,.0f}", ha="center", fontsize=9)
ax.text(len(values), values[-1] + 150, f"{values[-1]:,.0f}", ha="center", fontsize=9)
ax.set_xticks(range(len(steps)))
ax.set_xticklabels(steps, fontsize=9)
ax.set_ylabel("kWh per year")
ax.set_ylim(0, values[0] * 1.15)
ax.set_title("Where the energy goes: fixed panels in Phoenix")
save(fig, "loss_waterfall_phoenix.png")

# 5. tilt sweep, both sites ------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(7, 3.8))
for site, col in zip(SITES, ["#2a78d6", "#eb6834"]):
    s = sweep[site] / sweep[site].max() * 100
    ax.plot(s.index, s.values, color=col, label=site)
    best = s.idxmax()
    ax.plot([best], [100], "o", color=col, markersize=8, markeredgecolor=SURFACE, markeredgewidth=2)
    ax.annotate(f"best {best}°", (best, 100), xytext=(0, 8), textcoords="offset points", ha="center", fontsize=9, color=INK2)
ax.set_title("Fixed panels facing south: energy vs tilt")
ax.set_xlabel("Tilt from horizontal (degrees)")
ax.set_ylabel("% of the best tilt's energy")
ax.set_ylim(75, 103)
ax.legend(loc="lower center")
save(fig, "tilt_sweep.png")

# 6. pointing error vs energy, with the controllers marked ---------------------------------
fig, ax = plt.subplots(figsize=(8, 4))
ax.plot(pointing.pointing_error_deg, pointing.loss_pct, color="#2a78d6", label="Annual energy lost (Phoenix, dual axis)")
marks = [("Cloudy, calculated sun position", "Calculated sun position", "#1baf7a"),
         ("Clear, light sensors", "Light sensors, clear", "#eda100"),
         ("Cloudy, light sensors, raw", "Light sensors, cloudy, raw", "#e34948"),
         ("Cloudy, light sensors, filtered", "Light sensors, cloudy, filtered", "#6250d6")]
for key, label, col in marks:
    row = controllers[controllers.scenario == key].iloc[0]
    ax.plot([row.mean_error_deg], [row.annual_loss_pct], "o", color=col, markersize=8,
            markeredgecolor=SURFACE, markeredgewidth=2, label=f"{label}: {row.mean_error_deg:.1f}°, {row.annual_loss_pct:.2f}%")
ax.set_xlim(0, 20)
ax.set_ylim(0, 5)
ax.set_xlabel("Average pointing error (degrees)")
ax.set_ylabel("Energy lost per year (%)")
ax.set_title("Pointing error barely costs energy until it passes about 10°")
ax.legend(loc="upper left", fontsize=8)
save(fig, "pointing_error.png")

# 7. motor activity by controller -------------------------------------------------------------
fig, ax = plt.subplots(figsize=(8, 3.4))
order = ["Cloudy, calculated sun position", "Clear, light sensors", "Cloudy, light sensors, filtered", "Cloudy, light sensors, raw"]
labels = ["Calculated sun position (cloudy)", "Light sensors (clear)", "Light sensors, filtered (cloudy)", "Light sensors, raw (cloudy)"]
c = controllers.set_index("scenario").loc[order]
y = np.arange(len(order))
ax.barh(y, c.total_moves, color="#2a78d6", height=0.55)
for yi, (mv, rv) in enumerate(zip(c.total_moves, c.total_reversals)):
    ax.text(mv + 40, yi, f"{mv:,} moves, {rv} reversals", va="center", fontsize=9, color=INK2)
ax.set_yticks(y)
ax.set_yticklabels(labels)
ax.invert_yaxis()
ax.set_xlim(0, 4200)
ax.set_xlabel("Servo moves in one simulated day (pan + tilt)")
ax.set_title("Motor activity by controller")
ax.grid(axis="y", visible=False)
save(fig, "controller_moves.png")

# 8. break-even tracker premium vs what trackers really cost ----------------------------------
fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
for ax, market in zip(axes, ["Residential", "Utility scale"]):
    e = econ[econ.market == market].reset_index(drop=True)
    if market == "Utility scale":
        e = e[e.setup == "Single axis"].reset_index(drop=True)
    labels = [f"{r.site.split(',')[0]}, {r.setup.lower()}" for r in e.itertuples()]
    y = np.arange(len(e))
    for yi, r in zip(y, e.itertuples()):
        ax.plot([r.market_premium_low_per_w, r.market_premium_high_per_w], [yi, yi], color=NEUTRAL, linewidth=8, solid_capstyle="round")
        ax.plot([r.breakeven_premium_per_w], [yi], "D", color="#2a78d6", markersize=8, markeredgecolor=SURFACE, markeredgewidth=1.5)
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_ylim(len(e) - 0.4, -0.6)
    ax.set_xlim(0, None)
    ax.set_xlabel("Extra cost per watt of panels ($/W)")
    ax.set_title(market)
    ax.grid(axis="y", visible=False)
axes[0].plot([], [], "D", color="#2a78d6", label="Most it can cost and still pay back in 25 years")
axes[0].plot([], [], color=NEUTRAL, linewidth=8, label="What trackers actually add (market range)")
fig.legend(*axes[0].get_legend_handles_labels(), loc="lower center", ncol=2, bbox_to_anchor=(0.5, 0))
fig.suptitle("Is the tracker worth its price?", x=0.01, ha="left", fontweight="bold", fontsize=12)
save(fig, "breakeven.png", rect=(0, 0.1, 1, 1))

print("Saved:", ", ".join(sorted(p.name for p in FIG.glob("*.png"))))
