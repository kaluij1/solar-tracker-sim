/*
 * The controller on a real day: what does twitching cost in energy?
 *
 * Joins the two halves of the project. For one site and day of the typical year:
 *   - the sun angle the tracker must follow is the single axis rotation from solar-model.js
 *   - clouds come from that hour's weather: the diffuse share of sunlight, dhi / ghi, sets how
 *     strongly the cloud noise dims the sensors (assumption: 15% diffuse = clear, 100% = 80% dimming)
 *   - sensor brightness follows global sunlight (assumption: 400 lux units at 1000 W/m2, as in the sweep)
 *   - reflection flicker is not in weather data, so it stays a chosen value
 *
 * The real sun moves only 15 degrees an hour, so the controller is run in real time: every
 * 15 minutes of daylight, 30 seconds of control (1 ms steps) starting on target; the first 5 s
 * settle, the rest are measured. The pointing error found in each window is applied to that
 * 15 minutes, and power comes from solar-model.js with the panel at the controller's angle
 * (limited to +/-60 degrees like the tracker in the energy model) instead of the ideal one.
 */
(function (root) {
  "use strict";
  var M = root.SolarModel || (typeof require !== "undefined" && require("./solar-model.js"));
  var CM = root.ControllerModel || (typeof require !== "undefined" && require("./controller-model.js"));
  var SLOT_H = 0.25, WINDOW_MS = 30000, SETTLE_MS = 5000, SAMPLE_MS = 1000;

  function cloudFor(w) { return w.ghi > 1 ? Math.max(0, Math.min(80, 80 * (w.dhi / w.ghi - 0.15) / 0.85)) : 80; }
  function luxFor(w) { return Math.max(5, 400 * w.ghi / 1000); }
  function ideal(sun) { return M.rowTracker(sun, 0.01, "true", "linear").ideal; }   // rotation toward the sun, degrees
  function orientationAt(rot) {
    var r = Math.max(-60, Math.min(60, rot));
    return { tilt: Math.abs(r), azimuth: r >= 0 ? 90 : 270 };
  }

  // the list of 15 minute daylight slots for one day, with the sun and weather at each
  function slots(siteName, day, P) {
    var site = P.sites[siteName], out = [];
    for (var h = SLOT_H / 2; h < 24; h += SLOT_H) {
      var hoy = (day - 1) * 24 + h, sun = M.sunPosition(M.utcMsFor(site, hoy), site.lat, site.lon);
      if (sun.zenith >= 88) continue;
      var w = M.weatherAtHour(site, hoy);
      out.push({ hour: h, sun: sun, w: w, rot: ideal(sun), cloud: cloudFor(w), lux: luxFor(w) });
    }
    return out;
  }

  // run one controller through one slot; returns {err, reversals, moves, rots: [panel angle samples]}
  function runSlot(slot, next, mode, flicker, seed) {
    var s = CM.create({ mode: mode, lux: slot.lux, cloud: slot.cloud, flicker: flicker, externalSun: true, seed: seed });
    var rate = next ? (next.rot - slot.rot) / (SLOT_H * 3600000) : 0;     // degrees per ms, the real sun's speed
    s.sun = slot.rot; s.panel = slot.rot; s.commanded = Math.round(slot.rot) + 90;
    var errSum = 0, n = 0, rots = [], rev0 = 0, mov0 = 0;
    for (var t = 0; t < WINDOW_MS; t++) {
      s.sun = slot.rot + rate * t;
      CM.tick(s);
      if (t === SETTLE_MS) { rev0 = s.reversals; mov0 = s.moves; }
      if (t > SETTLE_MS) {
        errSum += Math.abs(s.sun - s.panel); n++;
        if (t % SAMPLE_MS === 0) rots.push(s.panel - s.sun);
      }
    }
    return { err: errSum / n, reversals: s.reversals - rev0, moves: s.moves - mov0, offsets: rots };
  }

  // whole day for each controller; onProgress(fraction) is optional. Returns a promise in the browser.
  function runDay(siteName, day, P, flicker, modes, onProgress, chunked) {
    var list = slots(siteName, day, P), res = {}, perfectKwh = 0;
    list.forEach(function (sl) { perfectKwh += M.step(sl.w, sl.sun, orientationAt(sl.rot), day, P).pac / 1000 * SLOT_H; });
    modes.forEach(function (m) { res[m] = { kwh: 0, errSum: 0, reversals: 0, moves: 0, worst: 0 }; });
    var jobs = [];
    list.forEach(function (sl, i) { modes.forEach(function (m, j) { jobs.push([i, m, 1000 * i + j + day * 7]); }); });
    function doJob(job) {
      var sl = list[job[0]], r = runSlot(sl, list[job[0] + 1], job[1], flicker, job[2]), acc = res[job[1]], p = 0;
      r.offsets.forEach(function (off) { p += M.step(sl.w, sl.sun, orientationAt(sl.rot + off), day, P).pac / 1000; });
      acc.kwh += p / r.offsets.length * SLOT_H;
      acc.errSum += r.err; acc.worst = Math.max(acc.worst, r.err);
      acc.reversals += r.reversals; acc.moves += r.moves;
    }
    function finish() {
      var out = { site: siteName, day: day, slots: list.length, daylightHours: list.length * SLOT_H, perfectKwh: perfectKwh, controllers: {} };
      modes.forEach(function (m) {
        var a = res[m], measuredS = list.length * (WINDOW_MS - SETTLE_MS) / 1000;
        out.controllers[m] = { kwh: a.kwh, lossPct: 100 * (1 - a.kwh / perfectKwh), meanErrDeg: a.errSum / list.length,
                               reversalsPerHour: a.reversals / measuredS * 3600, movesPerHour: a.moves / measuredS * 3600 };
      });
      return out;
    }
    if (!chunked) { jobs.forEach(doJob); return finish(); }
    return new Promise(function (resolve) {
      var k = 0;
      (function chunk() {
        var t0 = Date.now();
        while (k < jobs.length && Date.now() - t0 < 30) doJob(jobs[k++]);
        if (onProgress) onProgress(k / jobs.length);
        if (k < jobs.length) setTimeout(chunk, 0); else resolve(finish());
      })();
    });
  }

  var api = { runDay: runDay, slots: slots, cloudFor: cloudFor, luxFor: luxFor, ideal: ideal };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.RealDay = api;
})(this);
