// Closed-loop test of the dual axis Sun + Sensor Head chip, run natively (no browser).
//
// The Wokwi API calls are replaced with small stubs, and the controller logic
// from wokwi/sketch.ino is copied into run_day(). The "Arduino" sends real servo
// pulse widths on both servo pins every 20 ms and reads the four LDR voltages
// through a 10-bit ADC every 30 ms, the same timing as the sketch.
//
// The chip prints its own pointing error (angle between the panel's facing
// direction and the sun) once per simulated second. chip_log() captures those
// lines, so the error is measured by the plant model itself.
//
// Build and run:  make test

#include <math.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// ---------- Wokwi API stubs ----------
static double sim_ns = 0;
static float pin_volts[8];
static float attrs[16];
static int n_attrs = 0, n_pins = 0;
static pin_watch_config_t pwm_watch;
static timer_config_t tick_timer;

pin_t pin_init(const char *name, uint32_t mode) { (void)name; (void)mode; return n_pins++; }
float pin_dac_write(pin_t pin, float v) { pin_volts[pin] = v; return v; }
bool pin_watch(pin_t pin, const pin_watch_config_t *cfg) { (void)pin; pwm_watch = *cfg; return true; }
uint32_t attr_init_float(const char *name, float def) { (void)name; attrs[n_attrs] = def; return n_attrs++; }
float attr_read_float(uint32_t a) { return attrs[a]; }
double get_sim_nanos_d(void) { return sim_ns; }
timer_t timer_init(const timer_config_t *cfg) { tick_timer = *cfg; return 0; }
void timer_start(const timer_t t, uint32_t us, bool repeat) { (void)t; (void)us; (void)repeat; }
buffer_t framebuffer_init(uint32_t *w, uint32_t *h) { *w = 200; *h = 100; return 0; }
void buffer_write(buffer_t b, uint32_t off, uint8_t *d, uint32_t len) { (void)b; (void)off; (void)d; (void)len; }

// ---------- capture the chip's once-per-second pointing error ----------
static int measuring = 0;
static double err_sum = 0, err_max = 0, capture_sum = 0;
static long err_n = 0;
static float errs[4000];

int chip_log(const char *fmt, ...) {
  char line[256];
  va_list ap;
  va_start(ap, fmt);
  vsnprintf(line, sizeof line, fmt, ap);
  va_end(ap);
  char *p = strstr(line, "pointing error=");
  if (p && measuring) {
    float e = strtof(p + strlen("pointing error="), NULL);
    err_sum += e;
    if (e > err_max) err_max = e;
    capture_sum += fmax(0.0, cos(e * 3.14159265358979 / 180.0));
    if (err_n < 4000) errs[err_n] = e;
    err_n++;
  }
  return 0;
}

// chip pin order: PAN, TILT, TOP_E, TOP_W, BOT_E, BOT_W
enum { PIN_PAN, PIN_TILT, PIN_TOP_E, PIN_TOP_W, PIN_BOT_E, PIN_BOT_W };
// chip attribute order (see chip_init)
enum { A_DAY, A_LAT, A_DECL, A_AZ, A_EL, A_LUX, A_CLOUD, A_FLICKER };

static void reset_chip(unsigned seed) {
  n_attrs = 0; n_pins = 0;
  srand(seed);
  chip_init();
}

static void send_pulse(int ms, pin_t pin, int angle_deg) {
  float width_us = 544.0f + (2400.0f - 544.0f) * angle_deg / 180.0f;
  sim_ns = ms * 1e6;
  pwm_watch.pin_change(pwm_watch.user_data, pin, 1);
  sim_ns += width_us * 1000.0;
  pwm_watch.pin_change(pwm_watch.user_data, pin, 0);
  sim_ns = ms * 1e6;
}

static int adc_brightness(int pin) { return 1023 - (int)(pin_volts[pin] / 5.0f * 1023.0f); }

// ---------- one axis of the sketch's controller ----------
typedef struct {
  int angle, min_angle, max_angle, last_dir;
  int hist[20], hist_i, hist_n;
  long hist_sum, moves, reversals;
} axis_t;

static void control_axis(axis_t *a, int error, int use_filter) {
  const int THRESHOLD = 10, WINDOW = 20, DEADBAND = 40;
  int signal = error, limit = THRESHOLD;
  if (use_filter) {
    a->hist_sum -= a->hist[a->hist_i]; a->hist[a->hist_i] = error; a->hist_sum += error;
    a->hist_i = (a->hist_i + 1) % WINDOW;
    if (a->hist_n < WINDOW) a->hist_n++;
    signal = (int)(a->hist_sum / a->hist_n);
    limit = DEADBAND;
  }
  int dir = signal > limit ? 1 : signal < -limit ? -1 : 0;
  if (!dir) return;
  a->angle += dir;
  if (a->angle < a->min_angle) a->angle = a->min_angle;
  if (a->angle > a->max_angle) a->angle = a->max_angle;
  a->moves++;
  if (a->last_dir && dir != a->last_dir) a->reversals++;
  a->last_dir = dir;
}

// Open loop control, the way utility-scale trackers work: no light sensors at all.
// Calculate where the sun is from the date, time and location, and point there.
static void move_to(axis_t *a, int target) {
  if (target < a->min_angle) target = a->min_angle;
  if (target > a->max_angle) target = a->max_angle;
  if (target == a->angle) return;
  int dir = target > a->angle ? 1 : -1;
  a->angle = target;
  a->moves++;
  if (a->last_dir && dir != a->last_dir) a->reversals++;
  a->last_dir = dir;
}

// Same sun path equations as the chip (latitude 45, a time lapse day of DAY_S seconds)
static void sun_position(float day_time_s, float day_s, float lat_deg, float decl_deg, float *az, float *el) {
  const float D = 3.14159265f / 180.0f;
  float lat = lat_deg * D, dec = decl_deg * D;
  float cos_h0 = (sinf(5 * D) - sinf(lat) * sinf(dec)) / (cosf(lat) * cosf(dec));
  float h0 = acosf(fmaxf(-1, fminf(1, cos_h0)));
  float h = -h0 + 2 * h0 * day_time_s / day_s;
  float east = -cosf(dec) * sinf(h);
  float north = cosf(lat) * sinf(dec) - sinf(lat) * cosf(dec) * cosf(h);
  float up = sinf(lat) * sinf(dec) + cosf(lat) * cosf(dec) * cosf(h);
  *el = asinf(fmaxf(-1, fminf(1, up))) / D;
  *az = atan2f(east, -north) / D;
}

enum { MODE_RAW, MODE_FILTERED, MODE_CALCULATED };
static int csv_output = 0;

static int cmp_float(const void *x, const void *y) {
  float a = *(const float *)x, b = *(const float *)y;
  return (a > b) - (a < b);
}

// ---------- scenario: one time lapse day ----------
static void run_day(const char *label, float decl, int mode, float cloud, float flicker) {
  int use_filter = (mode == MODE_FILTERED);
  const int DAY_S = 120;
  reset_chip(1);
  attrs[A_DAY] = DAY_S; attrs[A_LAT] = 45; attrs[A_DECL] = decl;
  attrs[A_LUX] = 400; attrs[A_CLOUD] = cloud; attrs[A_FLICKER] = flicker;

  axis_t pan = { .angle = 90, .min_angle = 0, .max_angle = 180 };
  axis_t tilt = { .angle = 45, .min_angle = 0, .max_angle = 90 };
  err_sum = err_max = capture_sum = 0; err_n = 0;

  for (int ms = 0; ms < DAY_S * 1000 - 1; ms++) {
    sim_ns = ms * 1e6;
    measuring = ms > 10000;                    // skip the first 10 s while it finds the sun
    if (ms % 20 == 0) { send_pulse(ms, PIN_PAN, pan.angle); send_pulse(ms, PIN_TILT, tilt.angle); }
    tick_timer.callback(tick_timer.user_data);

    if (ms % 30 == 0 && mode == MODE_CALCULATED) {
      float az, el;
      sun_position((ms + 1) / 1000.0f, DAY_S, 45, decl, &az, &el);
      move_to(&pan, (int)lroundf(az + 90));
      move_to(&tilt, (int)lroundf(el));
    } else if (ms % 30 == 0) {                 // one pass of the sketch's loop()
      int tE = adc_brightness(PIN_TOP_E), tW = adc_brightness(PIN_TOP_W);
      int bE = adc_brightness(PIN_BOT_E), bW = adc_brightness(PIN_BOT_W);
      control_axis(&pan,  (tE + bE) / 2 - (tW + bW) / 2, use_filter);
      control_axis(&tilt, (tE + tW) / 2 - (bE + bW) / 2, use_filter);
    }
  }
  long n = err_n < 4000 ? err_n : 4000;
  qsort(errs, n, sizeof(float), cmp_float);
  const char *fmt = csv_output ? "\"%s\",%ld,%ld,%ld,%ld,%.2f,%.2f,%.2f\n"
                                : "| %-40s | %4ld / %4ld | %4ld / %4ld | %5.1f deg | %5.1f deg | %5.1f%% |\n";
  printf(fmt, label, pan.moves, tilt.moves, pan.reversals, tilt.reversals,
         err_sum / err_n, errs[(int)(0.95 * (n - 1))], 100.0 * capture_sum / err_n);
}

int main(int argc, char **argv) {
  csv_output = argc > 1 && strcmp(argv[1], "--csv") == 0;
  if (csv_output) {
    printf("scenario,pan_moves,tilt_moves,pan_reversals,tilt_reversals,mean_error_deg,p95_error_deg,capture_pct\n");
    run_day("Clear, light sensors",              0.0f, MODE_RAW,        0,  0);
    run_day("Cloudy, light sensors, raw",        0.0f, MODE_RAW,       30, 10);
    run_day("Cloudy, light sensors, filtered",   0.0f, MODE_FILTERED,  30, 10);
    run_day("Cloudy, calculated sun position",   0.0f, MODE_CALCULATED, 30, 10);
    return 0;
  }
  printf("One time lapse day (120 s) at 45 deg latitude, 400 lux. Error measured after 10 s.\n");
  printf("Capture = average of cos(pointing error), the share of direct sunlight a perfectly aimed panel would get.\n\n");
  printf("| %-40s | %-11s | %-11s | %-9s | %-9s | %-7s |\n",
         "Scenario", "Moves P/T", "Revs P/T", "Mean err", "95% err", "Capture");
  printf("|------------------------------------------|-------------|-------------|-----------|-----------|---------|\n");
  run_day("Equinox, clear, raw",                     0.0f, MODE_RAW,        0,  0);
  run_day("Equinox, 30% cloud 10% flicker, raw",     0.0f, MODE_RAW,       30, 10);
  run_day("Equinox, 30% cloud 10% flicker, filtered", 0.0f, MODE_FILTERED,  30, 10);
  run_day("Equinox, cloudy, calculated sun position", 0.0f, MODE_CALCULATED, 30, 10);
  run_day("Summer solstice, clear, raw",            23.4f, MODE_RAW,        0,  0);
  run_day("Winter solstice, clear, raw",           -23.4f, MODE_RAW,        0,  0);
  return 0;
}
