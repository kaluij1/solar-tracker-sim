/*
 * Browser port of the single axis hardware-in-the-loop simulation:
 *   plant      = single-axis/wokwi/sun-sensor-head.chip.c  (servo, divider wall, LDRs, clouds, flicker)
 *   controller = single-axis/wokwi/sketch.ino             (raw threshold, moving average + deadband)
 * plus a third controller that ignores the sensors and points at the calculated sun angle.
 * Constants are copied from the chip and the sketch.
 */
(function (root) {
  "use strict";
  var D2R = Math.PI / 180;
  var C = {
    VCC: 5, RL10: 50000, GAMMA: 0.7, FIXED: 10000,          // Wokwi photoresistor module
    WALL_RATIO: 3, DIFFUSE: 0.15,                           // assumptions (see README)
    TAU_RISE: 0.020, TAU_FALL: 0.050,                       // LDR lag, assumption
    SERVO_DPS: 600,                                         // SG90: 0.1 s per 60 deg
    FLICKER_TAU: 0.10, CLOUD_TAU: 3.0,                      // noise, assumptions
    LOOP_MS: 30, STEP_DEG: 1, THRESHOLD: 10, WINDOW: 20, DEADBAND: 40,   // sketch.ino
    SUN_START: -40, SUN_END: 40, SWEEP_S: 120               // the test's time lapse sweep
  };

  // seeded random numbers (mulberry32), so a run can be repeated exactly
  function rng(seed) {
    var a = seed >>> 0;
    return function () { a = (a + 0x6D2B79F5) >>> 0; var t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  }
  function gauss(s) {
    var u1 = s.rand() || 1e-9, u2 = s.rand();
    return Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2);
  }
  function ou(s, x, tau, sigma, dt) { return x - x / tau * dt + sigma * Math.sqrt(2 * dt / tau) * gauss(s); }
  function luxToVolts(lux) {
    lux = Math.max(lux, 0.01);
    var r = C.RL10 * Math.pow(lux / 10, -C.GAMMA);
    return C.VCC * r / (r + C.FIXED);
  }
  function adcBrightness(v) { return 1023 - Math.floor(v / 5 * 1023); }   // analogRead, flipped

  function create(opts) {
    var s = {
      mode: opts.mode || "raw",              // "raw" | "filtered" | "calculated"
      lux: opts.lux || 400, cloud: opts.cloud || 0, flicker: opts.flicker || 0,
      t: 0, sun: C.SUN_START,
      commanded: 90, panel: 0,               // servo angle (0..180) and panel angle (-90..90)
      cloudState: 0, fE: 0, fW: 0, luxE: opts.lux || 400, luxW: opts.lux || 400,
      hist: [], moves: 0, reversals: 0, lastDir: 0, errSum: 0, errN: 0,
      east: 0, west: 0, signal: 0,
      externalSun: !!opts.externalSun,       // true: the caller sets s.sun (and may change s.lux, s.cloud)
      rand: opts.seed != null ? rng(opts.seed) : Math.random
    };
    return s;
  }

  // advance one millisecond
  function tick(s) {
    var dt = 0.001;
    s.t += dt;
    if (!s.externalSun) {
      var frac = Math.min(s.t / C.SWEEP_S, 1);
      s.sun = C.SUN_START + (C.SUN_END - C.SUN_START) * frac;
    }

    // servo: slew toward the commanded angle
    var target = s.commanded - 90, maxStep = C.SERVO_DPS * dt, d = target - s.panel;
    s.panel += Math.max(-maxStep, Math.min(maxStep, d));

    // environment
    s.cloudState = ou(s, s.cloudState, C.CLOUD_TAU, 0.5, dt);
    var cloudiness = Math.min(1, Math.abs(s.cloudState));
    s.fE = ou(s, s.fE, C.FLICKER_TAU, s.flicker / 100, dt);
    s.fW = ou(s, s.fW, C.FLICKER_TAU, s.flicker / 100, dt);
    var sunLux = s.lux * (1 - s.cloud / 100 * cloudiness);
    s.sky = 1 - s.cloud / 100 * cloudiness;

    // divider wall shading
    var off = (s.sun - s.panel) * D2R;
    var direct = Math.max(0, Math.cos(off));
    var shade = Math.min(1, C.WALL_RATIO * Math.abs(Math.tan(off)));
    var dE = direct * (off < 0 ? 1 - shade : 1), dW = direct * (off > 0 ? 1 - shade : 1);
    var tE = sunLux * (C.DIFFUSE + (1 - C.DIFFUSE) * dE) * (1 + s.fE);
    var tW = sunLux * (C.DIFFUSE + (1 - C.DIFFUSE) * dW) * (1 + s.fW);
    s.luxE += (tE - s.luxE) * dt / (tE > s.luxE ? C.TAU_RISE : C.TAU_FALL);
    s.luxW += (tW - s.luxW) * dt / (tW > s.luxW ? C.TAU_RISE : C.TAU_FALL);

    // the sketch's loop() runs every 30 ms
    if (Math.round(s.t * 1000) % C.LOOP_MS === 0) control(s);
    if (s.t > 10) { s.errSum += Math.abs(s.sun - s.panel); s.errN++; }
  }

  function control(s) {
    var east = adcBrightness(luxToVolts(s.luxE)), west = adcBrightness(luxToVolts(s.luxW));
    s.east = east; s.west = west;
    var dir = 0;
    if (s.mode === "calculated") {
      var want = Math.round(s.sun + 90);
      if (want !== s.commanded) dir = want > s.commanded ? 1 : -1;
      if (dir) { s.commanded = want; count(s, dir); }
      s.signal = 0;
      return;
    }
    var error = east - west, signal = error, limit = C.THRESHOLD;
    if (s.mode === "filtered") {
      s.hist.push(error);
      if (s.hist.length > C.WINDOW) s.hist.shift();
      var sum = 0; for (var i = 0; i < s.hist.length; i++) sum += s.hist[i];
      signal = Math.trunc(sum / s.hist.length);
      limit = C.DEADBAND;
    }
    s.signal = signal;
    if (signal > limit) dir = 1; else if (signal < -limit) dir = -1;
    if (dir) {
      s.commanded = Math.max(0, Math.min(180, s.commanded + dir * C.STEP_DEG));
      count(s, dir);
    }
  }
  function count(s, dir) {
    s.moves++;
    if (s.lastDir && dir !== s.lastDir) s.reversals++;
    s.lastDir = dir;
  }

  var api = { create: create, tick: tick, C: C };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.ControllerModel = api;
})(this);
