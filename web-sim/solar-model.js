/*
 * Browser port of the energy model in energy-yield/energy_model.py.
 *
 * Same chain, same equations, same real hourly weather (NSRDB typical year):
 *   1. sun position          NOAA solar calculator equations (Meeus); pvlib uses NREL SPA
 *   2. panel orientation     flat, fixed tilt, single axis (N-S, +/-60 deg), dual axis
 *      2b. trackers in rows  row-to-row beam shading, with or without backtracking
 *   3. light on the panel    beam + Perez 1990 sky diffuse + ground reflection (as pvlib.irradiance)
 *   4. glass reflection      physical IAM (De Soto 2006) and Marion 2017 diffuse factors (table from pvlib)
 *   5. cell temperature      Sandia Array Performance Model, open rack glass/polymer
 *   6. DC power              PVWatts DC equation with the module's own temperature coefficient
 *                            (pvlib uses the CEC single diode model here: the one simplification)
 *   7. system losses         14.08 % PVWatts defaults
 *   8. AC power              PVWatts inverter equation, capped at the inverter rating
 *                            (pvlib uses the Sandia inverter model: needs the single diode voltage)
 *
 * Works in the browser (window.SolarModel) and in Node (require), so the same file is
 * validated against pvlib by validate.js.
 */
(function (root) {
  "use strict";
  var D2R = Math.PI / 180, R2D = 180 / Math.PI;
  function sind(x) { return Math.sin(x * D2R); }
  function cosd(x) { return Math.cos(x * D2R); }
  function tand(x) { return Math.tan(x * D2R); }

  /* ---------- 1. sun position (NOAA / Meeus) ---------- */
  // utcMs: milliseconds since 1970-01-01 UTC. Returns apparent zenith and azimuth (deg, from north).
  function sunPosition(utcMs, lat, lon) {
    var jd = utcMs / 86400000 + 2440587.5;
    var T = (jd - 2451545) / 36525;
    var L0 = (280.46646 + T * (36000.76983 + T * 0.0003032)) % 360;
    var M = 357.52911 + T * (35999.05029 - 0.0001537 * T);
    var e = 0.016708634 - T * (0.000042037 + 0.0000001267 * T);
    var C = sind(M) * (1.914602 - T * (0.004817 + 0.000014 * T)) + sind(2 * M) * (0.019993 - 0.000101 * T) + sind(3 * M) * 0.000289;
    var omega = 125.04 - 1934.136 * T;
    var lambda = L0 + C - 0.00569 - 0.00478 * sind(omega);
    var eps0 = 23 + (26 + (21.448 - T * (46.815 + T * (0.00059 - T * 0.001813))) / 60) / 60;
    var eps = eps0 + 0.00256 * cosd(omega);
    var decl = Math.asin(sind(eps) * sind(lambda)) * R2D;
    var y = Math.pow(tand(eps / 2), 2);
    var eot = 4 * R2D * (y * sind(2 * L0) - 2 * e * sind(M) + 4 * e * y * sind(M) * cosd(2 * L0)
      - 0.5 * y * y * sind(4 * L0) - 1.25 * e * e * sind(2 * M));            // minutes
    var minutesUtc = ((utcMs / 60000) % 1440 + 1440) % 1440;
    var tst = ((minutesUtc + eot + 4 * lon) % 1440 + 1440) % 1440;
    var H = tst / 4 < 0 ? tst / 4 + 180 : tst / 4 - 180;                    // hour angle
    var cz = sind(lat) * sind(decl) + cosd(lat) * cosd(decl) * cosd(H);
    cz = Math.max(-1, Math.min(1, cz));
    var zen = Math.acos(cz) * R2D;
    var az;
    var denom = cosd(lat) * sind(zen);
    if (Math.abs(denom) > 1e-6) {
      var ca = (sind(lat) * cz - sind(decl)) / denom;
      ca = Math.max(-1, Math.min(1, ca));
      var a = Math.acos(ca) * R2D;
      az = H > 0 ? (a + 180) % 360 : (540 - a) % 360;
    } else {
      az = lat > 0 ? 180 : 0;
    }
    // atmospheric refraction (NOAA approximation)
    var el = 90 - zen, refr = 0;
    if (el <= 85) {
      var te = tand(el);
      if (el > 5) refr = 58.1 / te - 0.07 / Math.pow(te, 3) + 0.000086 / Math.pow(te, 5);
      else if (el > -0.575) refr = 1735 + el * (-518.2 + el * (103.4 + el * (-12.79 + el * 0.711)));
      else refr = -20.772 / te;
      refr /= 3600;
    }
    return { zenith: zen - refr, azimuth: az, declination: decl };
  }

  /* ---------- 2. orientation ---------- */
  var SETUPS = ["Flat", "Fixed, best tilt", "Single axis", "Dual axis"];
  function orientation(setup, sun, bestTilt) {
    if (setup === "Flat") return { tilt: 0, azimuth: 180 };
    if (setup === "Fixed, best tilt") return { tilt: bestTilt, azimuth: 180 };
    if (sun.zenith > 90) return setup === "Single axis" ? { tilt: 0, azimuth: 180 } : { tilt: 0, azimuth: 180 };
    if (setup === "Single axis") {
      // horizontal north-south axis: rotate toward the sun's east-west component
      var east = sind(sun.zenith) * sind(sun.azimuth), up = cosd(sun.zenith);
      var theta = Math.atan2(east, up) * R2D;
      theta = Math.max(-60, Math.min(60, theta));
      return { tilt: Math.abs(theta), azimuth: theta >= 0 ? 90 : 270, rotation: theta };
    }
    return { tilt: Math.min(sun.zenith, 90), azimuth: sun.azimuth };   // dual axis
  }

  /* ---------- 2b. single axis trackers standing in rows ---------- */
  // gcr: ground coverage ratio = panel width / distance between rows.
  // strategy "true": every row points at the sun, so rows shade each other when the sun is low.
  // strategy "backtrack": rows turn back toward flat just enough to keep the next row unshaded
  //   (Anderson and Mikofski 2020, Eq. 14, as in pvlib.tracking.singleaxis).
  // Shaded fraction: Anderson and Jensen 2024, Eq. 12, flat ground (pvlib.shading.shaded_fraction1d).
  // shadeModel "linear": beam lost in proportion to the shaded area.
  // shadeModel "blocks": Martinez-Moreno et al. 2010, Eq. 6, with all 3 bypass blocks shaded
  //   (modules in portrait: the shadow edge runs along the row and crosses every block).
  var ROW_BLOCKS = 3;
  function rowTracker(sun, gcr, strategy, shadeModel) {
    if (sun.zenith >= 90) return { tilt: 0, azimuth: 180, rotation: 0, ideal: 0, shaded: 0, beamFactor: 1 };
    var east = sind(sun.zenith) * sind(sun.azimuth), up = cosd(sun.zenith);
    var ideal = Math.atan2(east, up) * R2D, theta = ideal;
    if (strategy === "backtrack") {
      var temp = Math.abs(cosd(ideal)) / gcr;
      if (temp < 1) theta = ideal - (ideal >= 0 ? 1 : -1) * Math.acos(temp) * R2D;
    }
    theta = Math.max(-60, Math.min(60, theta));
    var c = Math.max(1e-6, Math.abs(cosd(theta - ideal)));
    var fs = 1 - cosd(ideal) / (gcr * c);
    fs = fs < 1e-6 ? 0 : Math.min(1, fs);
    var bf = 1 - fs;
    if (shadeModel === "blocks" && fs > 0) bf *= 1 - ROW_BLOCKS / (1 + ROW_BLOCKS);
    return { tilt: Math.abs(theta), azimuth: theta >= 0 ? 90 : 270, rotation: theta, ideal: ideal, shaded: fs, beamFactor: bf };
  }

  /* ---------- 3. light on the panel ---------- */
  var F1C = [[-0.008, 0.588, -0.062], [0.13, 0.683, -0.151], [0.33, 0.487, -0.221], [0.568, 0.187, -0.295],
             [0.873, -0.392, -0.362], [1.132, -1.237, -0.412], [1.06, -1.6, -0.359], [0.678, -0.327, -0.25]];
  var F2C = [[-0.06, 0.072, -0.022], [-0.019, 0.066, -0.029], [0.055, -0.064, -0.026], [0.109, -0.152, -0.014],
             [0.226, -0.462, 0.001], [0.288, -0.823, 0.056], [0.264, -1.127, 0.131], [0.156, -1.377, 0.251]];
  var EPS_EDGES = [1.065, 1.23, 1.5, 1.95, 2.8, 4.5, 6.2];

  function extraRadiation(doy) {                               // Spencer, as pvlib default
    var B = 2 * Math.PI / 365 * (doy - 1);
    return 1366.1 * (1.00011 + 0.034221 * Math.cos(B) + 0.00128 * Math.sin(B) + 0.000719 * Math.cos(2 * B) + 0.000077 * Math.sin(2 * B));
  }
  function airmass(zen) {                                      // Kasten & Young 1989
    if (zen > 90) return NaN;
    return 1 / (cosd(zen) + 0.50572 * Math.pow(6.07995 + (90 - zen), -1.6364));
  }
  function cosAoi(tilt, surfAz, zen, sunAz) {
    return cosd(zen) * cosd(tilt) + sind(zen) * sind(tilt) * cosd(sunAz - surfAz);
  }
  function perezSky(tilt, surfAz, dhi, dni, dniExtra, zen, sunAz, am) {
    if (!(am >= 0) || dhi <= 0) return 0;
    var kappa = 1.041, z = zen * D2R;
    var delta = dhi * am / dniExtra;
    var eps = ((dhi + dni) / dhi + kappa * z * z * z) / (1 + kappa * z * z * z);
    var bin = 0;
    while (bin < 7 && eps >= EPS_EDGES[bin]) bin++;
    var F1 = Math.max(0, F1C[bin][0] + F1C[bin][1] * delta + F1C[bin][2] * z);
    var F2 = F2C[bin][0] + F2C[bin][1] * delta + F2C[bin][2] * z;
    var A = Math.max(0, cosAoi(tilt, surfAz, zen, sunAz));
    var B = Math.max(cosd(zen), cosd(85));
    var sky = dhi * (0.5 * (1 - F1) * (1 + cosd(tilt)) + F1 * A / B + F2 * sind(tilt));
    return Math.max(sky, 0);
  }

  /* ---------- 4. glass reflection ---------- */
  function iamPhysical(aoi) {                                  // n = 1.526, K = 4, L = 2 mm
    var n = 1.526, K = 4, L = 0.002;
    var c1 = Math.max(0, cosd(aoi)), s1 = Math.sqrt(1 - c1 * c1);
    var s2 = s1 / n, c2 = Math.sqrt(1 - s2 * s2);
    var rs = Math.pow((c1 - n * c2) / (c1 + n * c2), 2);
    var rp = Math.pow((c2 - n * c1) / (c2 + n * c1), 2);
    var r0 = Math.pow((1 - n) / (1 + n), 2);
    var ts = (1 - rs) * Math.exp(-K * L / c2), tp = (1 - rp) * Math.exp(-K * L / c2), t0 = (1 - r0) * Math.exp(-K * L);
    var v = (ts + tp) / 2 / t0;
    return isFinite(v) ? v : 0;
  }

  /* ---------- one time step ---------- */
  // w: {ghi, dni, dhi, temp, wind, albedo}; sun: from sunPosition; o: orientation; P: parameters
  function step(w, sun, o, doy, P) {
    var zen = sun.zenith, tilt = o.tilt, az = o.azimuth;
    var ca = cosAoi(tilt, az, zen, sun.azimuth);
    var aoi = Math.acos(Math.max(-1, Math.min(1, ca))) * R2D;
    var direct = Math.max(0, w.dni * ca) * (o.beamFactor == null ? 1 : o.beamFactor);
    var sky = perezSky(tilt, az, w.dhi, w.dni, extraRadiation(doy), zen, sun.azimuth, airmass(zen));
    var ground = w.ghi * w.albedo * (1 - cosd(tilt)) / 2;
    var poa = direct + sky + ground;
    var ti = Math.max(0, Math.min(90, Math.round(tilt)));
    var eff = Math.max(0, direct * iamPhysical(aoi) + sky * P.iam_diffuse.sky[ti] + ground * P.iam_diffuse.ground[ti]);
    var tCell = poa * Math.exp(P.sapm.a + P.sapm.b * w.wind) + w.temp + poa / 1000 * P.sapm.deltaT;
    var pdc0 = P.module.pdc0_w;
    var pdc = eff / 1000 * pdc0 * (1 + P.module.gamma_pdc * (tCell - 25));
    pdc = Math.max(0, pdc) * (1 - P.losses_pct / 100);
    var invPdc0 = P.inverter.paco_w / 0.96, zeta = pdc / invPdc0;
    var pac = 0;
    if (pdc > 0) {
      var eta = 0.96 / 0.9637 * (-0.0162 * zeta - 0.0059 / zeta + 0.9858);
      pac = Math.max(0, Math.min(P.inverter.paco_w, eta * pdc));
    }
    var unclipped = pdc > 0 ? Math.max(0, 0.96 / 0.9637 * (-0.0162 * zeta - 0.0059 / zeta + 0.9858) * pdc) : 0;
    return { poa: poa, direct: direct, sky: sky, ground: ground, effective: eff, aoi: aoi,
             tCell: tCell, pdc: pdc, pac: pac, clipped: Math.max(0, unclipped - pac) };
  }

  /* ---------- weather access ---------- */
  function weatherAt(site, i) {
    return { ghi: site.ghi[i], dni: site.dni[i], dhi: site.dhi[i], temp: site.temp10[i] / 10,
             wind: site.wind10[i] / 10, albedo: site.albedo100[i] / 100 };
  }
  // Weather at any time within the year: linear interpolation between the hourly
  // values, which are averages centered on each half hour.
  function weatherAtHour(site, hourOfYear) {
    var x = hourOfYear - 0.5, i0 = Math.floor(x), f = x - i0;
    var a = weatherAt(site, Math.max(0, Math.min(8759, i0))), b = weatherAt(site, Math.max(0, Math.min(8759, i0 + 1)));
    var o = {};
    for (var k in a) o[k] = a[k] + (b[k] - a[k]) * f;
    return o;
  }
  // UTC milliseconds for a local standard time: hour of year (0 = midnight Jan 1)
  function utcMsFor(site, hourOfYear, year) {
    return Date.UTC(year || 2023, 0, 1) + (hourOfYear - site.utc_offset) * 3600000;
  }

  /* ---------- a full year, hour by hour (same timestamps as the pvlib run) ---------- */
  function annual(site, P) {
    var totals = {}, monthly = {}, i, s;
    SETUPS.forEach(function (k) { totals[k] = 0; monthly[k] = new Array(12).fill(0); });
    for (i = 0; i < 8760; i++) {
      var hourOfYear = i + 0.5, doy = Math.floor(i / 24) + 1;
      var sun = sunPosition(utcMsFor(site, hourOfYear), site.lat, site.lon);
      var w = weatherAt(site, i);
      var month = new Date(Date.UTC(2023, 0, 1) + i * 3600000).getUTCMonth();
      for (s = 0; s < SETUPS.length; s++) {
        var o = orientation(SETUPS[s], sun, site.best_tilt);
        var r = step(w, sun, o, doy, P);
        totals[SETUPS[s]] += r.pac / 1000;
        monthly[SETUPS[s]][month] += r.pac / 1000;
      }
    }
    return { totals: totals, monthly: monthly };
  }

  // A full year for single axis trackers in rows: the three cases of energy-yield/run_rows.py
  var ROW_CASES = {
    "True tracking, linear shade loss": ["true", "linear"],
    "True tracking, bypass block loss": ["true", "blocks"],
    "Backtracking": ["backtrack", "linear"]
  };
  function annualRows(site, P, gcr) {
    var totals = {}, shadedHours = {}, daylight = 0, k;
    for (k in ROW_CASES) { totals[k] = 0; shadedHours[k] = 0; }
    for (var i = 0; i < 8760; i++) {
      var sun = sunPosition(utcMsFor(site, i + 0.5), site.lat, site.lon);
      if (sun.zenith >= 90) continue;
      daylight++;
      var w = weatherAt(site, i), doy = Math.floor(i / 24) + 1;
      for (k in ROW_CASES) {
        var o = rowTracker(sun, gcr, ROW_CASES[k][0], ROW_CASES[k][1]);
        totals[k] += step(w, sun, o, doy, P).pac / 1000;
        if (o.shaded > 0) shadedHours[k]++;
      }
    }
    return { totals: totals, shadedHours: shadedHours, daylightHours: daylight };
  }

  var api = { rowTracker: rowTracker, annualRows: annualRows, ROW_CASES: ROW_CASES,
               sunPosition: sunPosition, orientation: orientation, step: step, weatherAt: weatherAt,
              weatherAtHour: weatherAtHour, utcMsFor: utcMsFor, annual: annual, SETUPS: SETUPS,
              iamPhysical: iamPhysical, perezSky: perezSky, airmass: airmass, extraRadiation: extraRadiation };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.SolarModel = api;
})(this);
