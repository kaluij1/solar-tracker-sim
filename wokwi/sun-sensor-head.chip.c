// Sun + Sensor Head: a hardware-in-the-loop "plant model" for the solar tracker.
//
// It closes the loop the plain Wokwi parts can't:
//   1. reads the servo PWM signal coming out of Arduino pin 9
//   2. turns the panel at a realistic servo speed
//   3. works out how much sunlight hits each photoresistor, including the
//      shadow of the divider wall between them
//   4. adds clouds, reflection flicker, and the LDR's slow response
//   5. converts lux -> LDR resistance -> divider voltage, and outputs it on EAST/WEST
//
// The LDR math matches Wokwi's photoresistor module (rl10 = 50k, gamma = 0.7,
// 10k fixed resistor), so the Arduino sketch works unchanged.

#include "wokwi-api.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define TICK_US       1000      // physics update every 1 ms
#define DRAW_EVERY    50        // redraw the display every 50 ticks (20 fps)
#define DEG           (3.14159265f / 180.0f)

// ---------- physical constants ----------
#define VCC               5.0f
#define RL10_OHMS         50000.0f  // LDR resistance at 10 lux
#define LDR_GAMMA         0.7f      // slope of log(R) vs log(lux)
#define FIXED_OHMS        10000.0f  // divider resistor on the module
#define WALL_RATIO        3.0f      // divider wall height / LDR distance from the wall
#define DIFFUSE_FRACTION  0.15f     // sky light that arrives from all directions
#define LDR_TAU_RISE_S    0.020f    // CdS cells brighten in about 20 ms
#define LDR_TAU_FALL_S    0.050f    // and darken more slowly
#define SERVO_SPEED_DPS   600.0f    // SG90 class servo: about 0.1 s per 60 degrees
#define SERVO_MIN_US      544.0f    // Arduino Servo library pulse range
#define SERVO_MAX_US      2400.0f
#define FLICKER_TAU_S     0.10f     // reflections change over about 100 ms
#define CLOUD_TAU_S       3.0f      // clouds drift over a few seconds

typedef struct {
  pin_t pin_pwm, pin_east, pin_west;
  uint32_t attr_sun_angle, attr_sun_lux, attr_cloud, attr_flicker;

  uint64_t pulse_start_ns;
  float commanded_deg;   // servo angle the Arduino asked for (0 to 180)
  float panel_deg;       // where the panel actually is (-90 to 90, 0 = straight up)

  float cloud;           // 0 = clear, 1 = fully cloudy (slow random process)
  float flicker_e, flicker_w;
  float lux_e, lux_w;    // light each LDR is responding to (after its lag)

  buffer_t fb;
  uint32_t fb_w, fb_h;
  uint32_t *pixels;
  uint32_t tick;
} chip_t;

// ---------- helpers ----------
static float gauss(void) {                         // standard normal random number
  float u1 = (rand() + 1.0f) / ((float)RAND_MAX + 2.0f);
  float u2 = (rand() + 1.0f) / ((float)RAND_MAX + 2.0f);
  return sqrtf(-2.0f * logf(u1)) * cosf(2.0f * 3.14159265f * u2);
}

static float ou_step(float x, float tau, float sigma, float dt) {
  // Ornstein-Uhlenbeck process: random noise that drifts smoothly instead of jumping
  return x - x / tau * dt + sigma * sqrtf(2.0f * dt / tau) * gauss();
}

static float lux_to_volts(float lux) {
  if (lux < 0.01f) lux = 0.01f;
  float r_ldr = RL10_OHMS * powf(lux / 10.0f, -LDR_GAMMA);
  return VCC * r_ldr / (r_ldr + FIXED_OHMS);       // voltage divider, LDR on the low side
}

// ---------- servo PWM input ----------
static void on_pwm_edge(void *user_data, pin_t pin, uint32_t value) {
  chip_t *c = (chip_t *)user_data;
  uint64_t now = get_sim_nanos();
  if (value) {
    c->pulse_start_ns = now;                       // rising edge: pulse starts
  } else {
    float width_us = (now - c->pulse_start_ns) / 1000.0f;
    if (width_us > 400.0f && width_us < 2600.0f) { // ignore anything that isn't a servo pulse
      float deg = (width_us - SERVO_MIN_US) / (SERVO_MAX_US - SERVO_MIN_US) * 180.0f;
      if (deg < 0) deg = 0;
      if (deg > 180) deg = 180;
      c->commanded_deg = deg;
    }
  }
}

// ---------- drawing ----------
static void put(chip_t *c, int x, int y, uint32_t rgba) {
  if (x >= 0 && y >= 0 && x < (int)c->fb_w && y < (int)c->fb_h) c->pixels[y * c->fb_w + x] = rgba;
}
static uint32_t rgb(int r, int g, int b) {
  return (uint32_t)r | ((uint32_t)g << 8) | ((uint32_t)b << 16) | 0xFF000000u;   // RGBA bytes
}
static void line(chip_t *c, float x0, float y0, float x1, float y1, uint32_t col, int thick) {
  int n = (int)(fabsf(x1 - x0) + fabsf(y1 - y0)) + 1;
  for (int i = 0; i <= n; i++) {
    float t = (float)i / n;
    int x = (int)(x0 + (x1 - x0) * t), y = (int)(y0 + (y1 - y0) * t);
    for (int dx = -thick; dx <= thick; dx++)
      for (int dy = -thick; dy <= thick; dy++) put(c, x + dx, y + dy, col);
  }
}
static void disc(chip_t *c, float cx, float cy, int r, uint32_t col) {
  for (int dy = -r; dy <= r; dy++)
    for (int dx = -r; dx <= r; dx++)
      if (dx * dx + dy * dy <= r * r) put(c, (int)cx + dx, (int)cy + dy, col);
}

static void draw(chip_t *c, float sun_deg, float sky_level) {
  int w = c->fb_w, h = c->fb_h;
  float cx = w / 2.0f, cy = h - 28.0f;

  int sky = (int)(60 + 140 * sky_level);
  for (int y = 0; y < h; y++)
    for (int x = 0; x < w; x++)
      c->pixels[y * w + x] = (y > cy + 14) ? rgb(40, 90, 40) : rgb(sky / 2, sky * 3 / 4, sky);

  // sun on its arc
  float s = sun_deg * DEG;
  disc(c, cx + 70 * sinf(s), cy - 70 * cosf(s), 7, rgb(255, 220, 60));

  // post and panel (panel line is perpendicular to the direction it faces)
  line(c, cx, cy, cx, cy + 14, rgb(150, 150, 150), 1);
  float p = c->panel_deg * DEG;
  float ex = cx + 26 * cosf(p), ey = cy + 26 * sinf(p);   // east end
  float wx = cx - 26 * cosf(p), wy = cy - 26 * sinf(p);   // west end
  line(c, wx, wy, ex, ey, rgb(20, 40, 120), 1);

  // LDRs glow with the light they receive
  float full = attr_read_float(c->attr_sun_lux) + 1.0f;
  int ge = (int)fminf(255, 60 + 195 * c->lux_e / full);
  int gw = (int)fminf(255, 60 + 195 * c->lux_w / full);
  disc(c, ex, ey, 3, rgb(ge, ge, 0));
  disc(c, wx, wy, 3, rgb(gw, gw, 0));

  // ray from panel center along the panel's facing direction
  line(c, cx, cy, cx + 18 * sinf(p), cy - 18 * cosf(p), rgb(255, 255, 255), 0);

  buffer_write(c->fb, 0, (uint8_t *)c->pixels, w * h * 4);
}

// ---------- main physics tick ----------
static void on_tick(void *user_data) {
  chip_t *c = (chip_t *)user_data;
  const float dt = TICK_US / 1e6f;

  // 1. servo: move toward the commanded angle at a limited speed
  float target = c->commanded_deg - 90.0f;                   // servo 90 = panel facing straight up
  float max_step = SERVO_SPEED_DPS * dt;
  float diff = target - c->panel_deg;
  c->panel_deg += (diff > max_step) ? max_step : (diff < -max_step) ? -max_step : diff;

  // 2. environment: clouds (slow, shared) and reflections (fast, separate per sensor)
  float cover = attr_read_float(c->attr_cloud) / 100.0f;
  float flick = attr_read_float(c->attr_flicker) / 100.0f;
  c->cloud = ou_step(c->cloud, CLOUD_TAU_S, 0.5f, dt);
  float cloudiness = fminf(1.0f, fabsf(c->cloud));
  c->flicker_e = ou_step(c->flicker_e, FLICKER_TAU_S, flick, dt);
  c->flicker_w = ou_step(c->flicker_w, FLICKER_TAU_S, flick, dt);

  float sun_deg = attr_read_float(c->attr_sun_angle);
  float sun_lux = attr_read_float(c->attr_sun_lux) * (1.0f - cover * cloudiness);

  // 3. geometry: both LDRs face the same way as the panel, with an opaque wall
  //    between them. When the sun is off to one side, the wall's shadow covers
  //    part of the LDR on the far side. Shaded fraction = wall height * tan(angle) / distance.
  float off = (sun_deg - c->panel_deg) * DEG;          // how far the sun is from the panel's aim
  float direct = fmaxf(0.0f, cosf(off));                // light on an unshaded sensor
  float shade = fminf(1.0f, WALL_RATIO * fabsf(tanf(off)));
  float direct_e = direct * (off < 0 ? 1.0f - shade : 1.0f);   // sun to the west shades the east LDR
  float direct_w = direct * (off > 0 ? 1.0f - shade : 1.0f);   // sun to the east shades the west LDR
  float target_e = sun_lux * (DIFFUSE_FRACTION + (1 - DIFFUSE_FRACTION) * direct_e) * (1 + c->flicker_e);
  float target_w = sun_lux * (DIFFUSE_FRACTION + (1 - DIFFUSE_FRACTION) * direct_w) * (1 + c->flicker_w);

  // 4. LDR response lag (faster getting brighter than getting darker)
  c->lux_e += (target_e - c->lux_e) * dt / (target_e > c->lux_e ? LDR_TAU_RISE_S : LDR_TAU_FALL_S);
  c->lux_w += (target_w - c->lux_w) * dt / (target_w > c->lux_w ? LDR_TAU_RISE_S : LDR_TAU_FALL_S);

  // 5. electrical output
  pin_dac_write(c->pin_east, lux_to_volts(c->lux_e));
  pin_dac_write(c->pin_west, lux_to_volts(c->lux_w));

  if (++c->tick % DRAW_EVERY == 0) draw(c, sun_deg, 1.0f - cover * cloudiness);
  if (c->tick % 1000 == 0)
    printf("sun=%5.1f  panel=%5.1f  pointing error=%5.1f deg  east=%6.0f lux  west=%6.0f lux\n",
           sun_deg, c->panel_deg, sun_deg - c->panel_deg, c->lux_e, c->lux_w);
}

void chip_init(void) {
  chip_t *c = calloc(1, sizeof(chip_t));

  c->pin_pwm  = pin_init("PWM", INPUT);
  c->pin_east = pin_init("EAST", ANALOG);
  c->pin_west = pin_init("WEST", ANALOG);

  c->attr_sun_angle = attr_init_float("sunAngle", 30);
  c->attr_sun_lux   = attr_init_float("sunLux", 400);
  c->attr_cloud     = attr_init_float("cloudCover", 0);
  c->attr_flicker   = attr_init_float("reflections", 0);

  c->commanded_deg = 90;
  c->panel_deg = 0;
  c->lux_e = c->lux_w = 400;

  const pin_watch_config_t watch = { .user_data = c, .edge = BOTH, .pin_change = on_pwm_edge };
  pin_watch(c->pin_pwm, &watch);

  c->fb = framebuffer_init(&c->fb_w, &c->fb_h);
  c->pixels = malloc(c->fb_w * c->fb_h * 4);

  const timer_config_t timer = { .user_data = c, .callback = on_tick };
  timer_start(timer_init(&timer), TICK_US, true);

  printf("Sun + Sensor Head ready\n");
}
