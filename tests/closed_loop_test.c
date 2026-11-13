// Closed-loop test of the Sun + Sensor Head chip, run natively (no browser).
//
// The Wokwi API calls are replaced with small stubs, and the controller logic
// from wokwi/sketch.ino is copied into run_scenario(). The "Arduino" sends real
// servo pulse widths every 20 ms and reads the chip's voltages through a
// 10-bit ADC every 30 ms, the same timing as the sketch.
//
// The chip's printf() is redirected to chip_log() at compile time to keep the output clean.
//
// Build and run:  make test

#include "wokwi-api.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// ---------- Wokwi API stubs ----------
static double sim_ns = 0;
static float pin_volts[3];
static float attrs[8];
static int n_attrs = 0;
static pin_watch_config_t pwm_watch;
static timer_config_t tick_timer;

pin_t pin_init(const char *name, uint32_t mode) {
  (void)mode;
  if (!strcmp(name, "PWM")) return 0;
  if (!strcmp(name, "EAST")) return 1;
  return 2;
}
float pin_dac_write(pin_t pin, float v) { pin_volts[pin] = v; return v; }
bool pin_watch(pin_t pin, const pin_watch_config_t *cfg) { (void)pin; pwm_watch = *cfg; return true; }
uint32_t attr_init_float(const char *name, float def) { (void)name; attrs[n_attrs] = def; return n_attrs++; }
float attr_read_float(uint32_t a) { return attrs[a]; }
double get_sim_nanos_d(void) { return sim_ns; }
timer_t timer_init(const timer_config_t *cfg) { tick_timer = *cfg; return 0; }
void timer_start(const timer_t t, uint32_t us, bool repeat) { (void)t; (void)us; (void)repeat; }
int chip_log(const char *fmt, ...) { (void)fmt; return 0; }   // silences the chip's printf
buffer_t framebuffer_init(uint32_t *w, uint32_t *h) { *w = 160; *h = 120; return 0; }
void buffer_write(buffer_t b, uint32_t off, uint8_t *d, uint32_t len) { (void)b; (void)off; (void)d; (void)len; }

enum { SUN_ANGLE, SUN_LUX, CLOUD, FLICKER };

static void reset_chip(unsigned seed) {
  n_attrs = 0;
  srand(seed);
  chip_init();
}

static void send_servo_pulse(int ms, int angle_deg) {
  float width_us = 544.0f + (2400.0f - 544.0f) * angle_deg / 180.0f;
  sim_ns = ms * 1e6;
  pwm_watch.pin_change(pwm_watch.user_data, 0, 1);
  sim_ns += width_us * 1000.0;
  pwm_watch.pin_change(pwm_watch.user_data, 0, 0);
  sim_ns = ms * 1e6;
}

static int adc_brightness(int pin) {        // analogRead(), flipped so bigger = brighter
  return 1023 - (int)(pin_volts[pin] / 5.0f * 1023.0f);
}

// ---------- scenario: sun sweeps -40 to +40 deg over 120 s ----------
static void run_scenario(const char *label, int use_filter, float lux, float cloud, float flicker) {
  const int THRESHOLD = 10, WINDOW = 20, DEADBAND = 40;
  reset_chip(1);
  attrs[SUN_LUX] = lux; attrs[CLOUD] = cloud; attrs[FLICKER] = flicker;

  int angle = 90, last_dir = 0, hist[20] = {0}, hist_i = 0, hist_n = 0;
  long hist_sum = 0, moves = 0, reversals = 0;
  double err_sum = 0; long err_n = 0;

  for (int ms = 0; ms < 120000; ms++) {
    sim_ns = ms * 1e6;
    attrs[SUN_ANGLE] = -40.0f + 80.0f * ms / 120000.0f;
    if (ms % 20 == 0) send_servo_pulse(ms, angle);
    tick_timer.callback(tick_timer.user_data);

    if (ms % 30 == 0) {                     // one pass of the sketch's loop()
      int err = adc_brightness(1) - adc_brightness(2);
      int signal = err, limit = THRESHOLD;
      if (use_filter) {
        hist_sum -= hist[hist_i]; hist[hist_i] = err; hist_sum += err;
        hist_i = (hist_i + 1) % WINDOW;
        if (hist_n < WINDOW) hist_n++;
        signal = (int)(hist_sum / hist_n);
        limit = DEADBAND;
      }
      int dir = signal > limit ? 1 : signal < -limit ? -1 : 0;
      if (dir) {
        angle += dir;
        if (angle < 0) angle = 0;
        if (angle > 180) angle = 180;
        moves++;
        if (last_dir && dir != last_dir) reversals++;
        last_dir = dir;
      }
      if (ms > 10000) { err_sum += fabs(attrs[SUN_ANGLE] - (angle - 90)); err_n++; }
    }
  }
  printf("| %-36s | %6ld | %9ld | %10.1f deg |\n", label, moves, reversals, err_sum / err_n);
}

// ---------- noise measurement: panel held on the sun ----------
static void measure_noise(float cloud, float flicker) {
  reset_chip(2);
  attrs[SUN_ANGLE] = 0; attrs[SUN_LUX] = 400; attrs[CLOUD] = cloud; attrs[FLICKER] = flicker;
  int hist[20] = {0}, hist_i = 0; long hist_sum = 0;
  double s1 = 0, s2 = 0, f1 = 0, f2 = 0; long n = 0;
  for (int ms = 0; ms < 300000; ms++) {
    sim_ns = ms * 1e6;
    if (ms % 20 == 0) send_servo_pulse(ms, 90);
    tick_timer.callback(tick_timer.user_data);
    if (ms % 30 == 0 && ms > 5000) {
      int err = adc_brightness(1) - adc_brightness(2);
      hist_sum -= hist[hist_i]; hist[hist_i] = err; hist_sum += err; hist_i = (hist_i + 1) % 20;
      double avg = hist_sum / 20.0;
      s1 += err; s2 += (double)err * err; f1 += avg; f2 += avg * avg; n++;
    }
  }
  printf("| %3.0f%% cloud, %3.0f%% flicker | %8.1f | %14.1f |\n", cloud, flicker,
         sqrt(s2 / n - (s1 / n) * (s1 / n)), sqrt(f2 / n - (f1 / n) * (f1 / n)));
}

int main(void) {
  printf("Tracking: sun sweeps -40 to +40 deg over 120 s (mean error measured after 10 s)\n\n");
  printf("| %-36s | %6s | %9s | %14s |\n", "Scenario", "Moves", "Reversals", "Mean error");
  printf("|--------------------------------------|--------|-----------|----------------|\n");
  run_scenario("Clear, 400 lux, raw", 0, 400, 0, 0);
  run_scenario("30% cloud, 10% flicker, raw", 0, 400, 30, 10);
  run_scenario("30% cloud, 10% flicker, filtered", 1, 400, 30, 10);
  run_scenario("Clear, 400 lux, filtered", 1, 400, 0, 0);
  run_scenario("Clear, 10000 lux, raw", 0, 10000, 0, 0);

  printf("\nSensor noise with the panel held on the sun (error in ADC counts, 1 std dev)\n\n");
  printf("| %-25s | %8s | %14s |\n", "Conditions", "Raw", "20-sample avg");
  printf("|---------------------------|----------|----------------|\n");
  measure_noise(0, 0);
  measure_noise(30, 10);
  measure_noise(50, 20);
  return 0;
}
