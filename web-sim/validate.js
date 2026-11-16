// Validate the browser model (solar-model.js) against the pvlib model.
//   node validate.js
// 1. Sun position vs NREL SPA (pvlib), sampled hourly through the year.
// 2. Annual AC energy for every site and setup vs pvlib's full model and its PVWatts cross-check.
// Writes validation.json, which the web page displays.
const fs = require("fs");
const path = require("path");
const M = require("./solar-model.js");

global.window = {};
eval(fs.readFileSync(path.join(__dirname, "weather-data.js"), "utf8"));
const P = window.SOLAR_DATA;
const out = { sun: {}, annual: {} };

// 1. sun position
const ref = JSON.parse(fs.readFileSync(path.join(__dirname, "check-sun.json"), "utf8"));
for (const [name, rows] of Object.entries(ref)) {
  const site = P.sites[name];
  let maxZ = 0, maxA = 0, n = 0;
  for (const [i, zen, az] of rows) {
    if (zen > 85) continue;                       // compare daylight hours only
    const s = M.sunPosition(M.utcMsFor(site, i + 0.5), site.lat, site.lon);
    maxZ = Math.max(maxZ, Math.abs(s.zenith - zen));
    let dA = Math.abs(s.azimuth - az); if (dA > 180) dA = 360 - dA;
    maxA = Math.max(maxA, dA); n++;
  }
  out.sun[name] = { hours_compared: n, max_zenith_error_deg: +maxZ.toFixed(3), max_azimuth_error_deg: +maxA.toFixed(3) };
}

// 2. annual energy
for (const [name, site] of Object.entries(P.sites)) {
  const r = M.annual(site, P);
  out.annual[name] = {};
  for (const k of M.SETUPS) {
    const js = r.totals[k], full = site.pvlib_annual_kwh[k], pvw = site.pvlib_pvwatts_kwh[k];
    out.annual[name][k] = { browser_kwh: +js.toFixed(1), pvlib_kwh: full, pvlib_pvwatts_kwh: pvw,
                            diff_vs_pvlib_pct: +(100 * (js / full - 1)).toFixed(2) };
  }
  const f = r.totals["Fixed, best tilt"];
  out.annual[name].gains = {
    single_axis_vs_fixed_browser_pct: +(100 * (r.totals["Single axis"] / f - 1)).toFixed(1),
    single_axis_vs_fixed_pvlib_pct: +(100 * (site.pvlib_annual_kwh["Single axis"] / site.pvlib_annual_kwh["Fixed, best tilt"] - 1)).toFixed(1),
    dual_axis_vs_fixed_browser_pct: +(100 * (r.totals["Dual axis"] / f - 1)).toFixed(1),
    dual_axis_vs_fixed_pvlib_pct: +(100 * (site.pvlib_annual_kwh["Dual axis"] / site.pvlib_annual_kwh["Fixed, best tilt"] - 1)).toFixed(1),
  };
}
const all = Object.values(out.annual).flatMap(s => M.SETUPS.map(k => Math.abs(s[k].diff_vs_pvlib_pct)));
out.max_abs_diff_pct = +Math.max(...all).toFixed(2);
fs.writeFileSync(path.join(__dirname, "validation.json"), JSON.stringify(out, null, 2));
console.log(JSON.stringify(out, null, 2));
