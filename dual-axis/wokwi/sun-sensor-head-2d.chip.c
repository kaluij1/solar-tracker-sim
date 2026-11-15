// Sun + Sensor Head (dual axis): hardware-in-the-loop plant model for a pan/tilt solar tracker.
//
// Every 1 ms it:
//   1. decodes two servo PWM signals (PAN on Arduino pin 9, TILT on pin 10)
//   2. moves the panel at a realistic servo speed on both axes
//   3. moves the sun, either from the manual sliders or along a real sun path
//      (latitude + season), compressed into a time lapse "day"
//   4. works out the light on four photoresistors arranged in quadrants with a
//      cross-shaped divider wall between them, including the wall's shadow
//   5. adds clouds, reflection flicker and LDR response lag
//   6. converts lux -> LDR resistance -> divider voltage on TOP_E, TOP_W, BOT_E, BOT_W
//
// Angles: azimuth is measured from due south, positive toward east.
// Elevation is measured up from the horizon.
// Pan servo 90 = facing south, pan servo 180 = facing east.
// Tilt servo 0 = facing the horizon, tilt servo 90 = facing straight up.

#include "wokwi-api.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define TICK_US           1000
#define DRAW_EVERY        50
#define PI_F              3.14159265f
#define DEG               (PI_F / 180.0f)

// ---------- physical constants ----------
#define VCC               5.0f
#define RL10_OHMS         50000.0f
#define LDR_GAMMA         0.7f
#define FIXED_OHMS        10000.0f
#define WALL_RATIO        3.0f      // divider wall height / LDR distance from the wall
#define DIFFUSE_FRACTION  0.15f
#define LDR_TAU_RISE_S    0.020f
#define LDR_TAU_FALL_S    0.050f
#define SERVO_SPEED_DPS   600.0f
#define SERVO_MIN_US      544.0f
#define SERVO_MAX_US      2400.0f
#define FLICKER_TAU_S     0.10f
#define CLOUD_TAU_S       3.0f
#define MIN_ELEVATION_DEG 5.0f      // time lapse day runs between these sun elevations

enum { TOP_E, TOP_W, BOT_E, BOT_W, N_LDR };

typedef struct { float x, y, z; } vec3;   // x = east, y = north, z = up

typedef struct {
  pin_t pin_pan, pin_tilt, pin_ldr[N_LDR];
  uint32_t attr_day, attr_lat, attr_decl, attr_az, attr_el, attr_lux, attr_cloud, attr_flicker;

  uint64_t pan_rise_ns, tilt_rise_ns;
  float pan_cmd, tilt_cmd;        // commanded servo angles (0 to 180)
  float pan_deg, tilt_deg;        // actual servo angles

  float sun_az, sun_el;           // current sun position (deg)
  float day_time_s;

  float cloud, flicker[N_LDR], lux[N_LDR];

  buffer_t fb;
  uint32_t fb_w, fb_h, *pixels, tick;
} chip_t;

// ---------- math helpers ----------
static float gauss(void) {
  float u1 = (rand() + 1.0f) / ((float)RAND_MAX + 2.0f);
  float u2 = (rand() + 1.0f) / ((float)RAND_MAX + 2.0f);
  return sqrtf(-2.0f * logf(u1)) * cosf(2.0f * PI_F * u2);
}
static float ou_step(float x, float tau, float sigma, float dt) {
  return x - x / tau * dt + sigma * sqrtf(2.0f * dt / tau) * gauss();
}
static float dot(vec3 a, vec3 b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
static float clampf(float v, float lo, float hi) { return v < lo ? lo : v > hi ? hi : v; }

// unit vector for an azimuth (from south, + east) and elevation
static vec3 direction(float az_deg, float el_deg) {
  float a = az_deg * DEG, e = el_deg * DEG;
  return (vec3){ cosf(e) * sinf(a), -cosf(e) * cosf(a), sinf(e) };
}

static float lux_to_volts(float lux) {
  if (lux < 0.01f) lux = 0.01f;
  float r_ldr = RL10_OHMS * powf(lux / 10.0f, -LDR_GAMMA);
  return VCC * r_ldr / (r_ldr + FIXED_OHMS);
}

// ---------- servo PWM input ----------
static void on_pwm_edge(void *user_data, pin_t pin, uint32_t value) {
  chip_t *c = (chip_t *)user_data;
  uint64_t now = get_sim_nanos();
  uint64_t *rise = (pin == c->pin_pan) ? &c->pan_rise_ns : &c->tilt_rise_ns;
  if (value) { *rise = now; return; }
  float width_us = (now - *rise) / 1000.0f;
  if (width_us < 400.0f || width_us > 2600.0f) return;
  float deg = clampf((width_us - SERVO_MIN_US) / (SERVO_MAX_US - SERVO_MIN_US) * 180.0f, 0, 180);
  if (pin == c->pin_pan) c->pan_cmd = deg; else c->tilt_cmd = deg;
}

static float slew(float actual, float target, float max_step) {
  float d = target - actual;
  return actual + clampf(d, -max_step, max_step);
}

// ---------- sun position ----------
static void update_sun(chip_t *c, float dt) {
  float day_len = attr_read_float(c->attr_day);
  if (day_len <= 0) {                                   // manual sliders
    c->sun_az = attr_read_float(c->attr_az);
    c->sun_el = attr_read_float(c->attr_el);
    return;
  }
  // Real sun path. Hour angle h runs from morning to evening; the day is
  // compressed so that the part above MIN_ELEVATION takes day_len seconds.
  float lat = attr_read_float(c->attr_lat) * DEG;
  float dec = attr_read_float(c->attr_decl) * DEG;
  float cos_h0 = (sinf(MIN_ELEVATION_DEG * DEG) - sinf(lat) * sinf(dec)) / (cosf(lat) * cosf(dec));
  float h0 = acosf(clampf(cos_h0, -1, 1));             // hour angle when the sun is at MIN_ELEVATION
  c->day_time_s = fmodf(c->day_time_s + dt, day_len);
  float h = -h0 + 2 * h0 * c->day_time_s / day_len;    // negative = morning

  float east  = -cosf(dec) * sinf(h);
  float north =  cosf(lat) * sinf(dec) - sinf(lat) * cosf(dec) * cosf(h);
  float up    =  sinf(lat) * sinf(dec) + cosf(lat) * cosf(dec) * cosf(h);
  c->sun_el = asinf(clampf(up, -1, 1)) / DEG;
  c->sun_az = atan2f(east, -north) / DEG;
}

// ---------- drawing ----------
static void put(chip_t *c, int x, int y, uint32_t col) {
  if (x >= 0 && y >= 0 && x < (int)c->fb_w && y < (int)c->fb_h) c->pixels[y * c->fb_w + x] = col;
}
static uint32_t rgb(int r, int g, int b) {
  return (uint32_t)r | ((uint32_t)g << 8) | ((uint32_t)b << 16) | 0xFF000000u;
}
static void line(chip_t *c, float x0, float y0, float x1, float y1, uint32_t col) {
  int n = (int)(fabsf(x1 - x0) + fabsf(y1 - y0)) + 1;
  for (int i = 0; i <= n; i++) {
    float t = (float)i / n;
    int x = (int)(x0 + (x1 - x0) * t), y = (int)(y0 + (y1 - y0) * t);
    put(c, x, y, col); put(c, x + 1, y, col); put(c, x, y + 1, col);
  }
}
static void disc(chip_t *c, float cx, float cy, int r, uint32_t col) {
  for (int dy = -r; dy <= r; dy++)
    for (int dx = -r; dx <= r; dx++)
      if (dx * dx + dy * dy <= r * r) put(c, (int)cx + dx, (int)cy + dy, col);
}

static void draw(chip_t *c, float sky_level) {
  int w = c->fb_w, h = c->fb_h;
  int sky = (int)(60 + 140 * sky_level);
  for (int y = 0; y < h; y++)
    for (int x = 0; x < w; x++)
      c->pixels[y * w + x] = (x == w / 2) ? rgb(0, 0, 0) : rgb(sky / 2, sky * 3 / 4, sky);

  float pan_az = c->pan_deg - 90.0f, tilt_el = c->tilt_deg;
  uint32_t sun_col = c->sun_el > 0 ? rgb(255, 220, 60) : rgb(90, 90, 110);
  uint32_t panel_col = rgb(20, 40, 120);

  // left half: top view (azimuth). South is down, east is right.
  float cx = w / 4.0f, cy = h / 2.0f, r = 40;
  for (int a = 0; a < 360; a += 3) put(c, (int)(cx + r * cosf(a * DEG)), (int)(cy + r * sinf(a * DEG)), rgb(230, 230, 230));
  disc(c, cx + r * sinf(c->sun_az * DEG), cy + r * cosf(c->sun_az * DEG), 5, sun_col);
  line(c, cx, cy, cx + 30 * sinf(pan_az * DEG), cy + 30 * cosf(pan_az * DEG), panel_col);
  disc(c, cx, cy, 2, rgb(150, 150, 150));

  // right half: side view (elevation). Horizon at the bottom.
  float sx = w * 0.75f - 35, sy = h - 12.0f;
  line(c, w / 2.0f + 2, sy, (float)w, sy, rgb(40, 90, 40));
  for (int a = 0; a <= 90; a += 3) put(c, (int)(sx + 75 * cosf(a * DEG)), (int)(sy - 75 * sinf(a * DEG)), rgb(230, 230, 230));
  if (c->sun_el > -5) disc(c, sx + 75 * cosf(c->sun_el * DEG), sy - 75 * sinf(c->sun_el * DEG), 5, sun_col);
  line(c, sx, sy, sx + 55 * cosf(tilt_el * DEG), sy - 55 * sinf(tilt_el * DEG), panel_col);

  // four LDR indicators in the top-right corner, brightness = light received
  float full = attr_read_float(c->attr_lux) + 1.0f;
  int pos[N_LDR][2] = { { w - 12, 8 }, { w - 22, 8 }, { w - 12, 18 }, { w - 22, 18 } };
  for (int i = 0; i < N_LDR; i++) {
    int g = (int)fminf(255, 40 + 215 * c->lux[i] / full);
    disc(c, pos[i][0], pos[i][1], 3, rgb(g, g, 0));
  }

  buffer_write(c->fb, 0, (uint8_t *)c->pixels, w * h * 4);
}

// ---------- main physics tick ----------
static void on_tick(void *user_data) {
  chip_t *c = (chip_t *)user_data;
  const float dt = TICK_US / 1e6f;

  // 1. servos
  c->pan_deg  = slew(c->pan_deg,  c->pan_cmd,  SERVO_SPEED_DPS * dt);
  c->tilt_deg = slew(c->tilt_deg, c->tilt_cmd, SERVO_SPEED_DPS * dt);

  // 2. sun and environment
  update_sun(c, dt);
  float cover = attr_read_float(c->attr_cloud) / 100.0f;
  float flick = attr_read_float(c->attr_flicker) / 100.0f;
  c->cloud = ou_step(c->cloud, CLOUD_TAU_S, 0.5f, dt);
  float cloudiness = fminf(1.0f, fabsf(c->cloud));
  float sun_lux = c->sun_el > 0 ? attr_read_float(c->attr_lux) * (1.0f - cover * cloudiness) : 0.0f;

  // 3. geometry in the panel's own frame:
  //    n = where the panel faces, u = toward its east side, v = toward its top edge
  float pan_az = c->pan_deg - 90.0f, tilt_el = c->tilt_deg;
  vec3 n = direction(pan_az, tilt_el);
  vec3 u = { cosf(pan_az * DEG), sinf(pan_az * DEG), 0 };
  vec3 v = { -sinf(tilt_el * DEG) * sinf(pan_az * DEG), sinf(tilt_el * DEG) * cosf(pan_az * DEG), cosf(tilt_el * DEG) };
  vec3 s = direction(c->sun_az, c->sun_el);

  float sn = dot(s, n), su = dot(s, u), sv = dot(s, v);
  float direct = fmaxf(0.0f, sn);
  float off_side = atan2f(su, sn);          // + = sun toward the panel's east side
  float off_up   = atan2f(sv, sn);          // + = sun toward the panel's top edge
  float shade_side = fminf(1.0f, WALL_RATIO * fabsf(tanf(off_side)));
  float shade_up   = fminf(1.0f, WALL_RATIO * fabsf(tanf(off_up)));
  if (sn <= 0) { shade_side = 1; shade_up = 1; }

  for (int i = 0; i < N_LDR; i++) {
    int is_east = (i == TOP_E || i == BOT_E);
    int is_top  = (i == TOP_E || i == TOP_W);
    // the vertical wall shades the side away from the sun, the horizontal wall the edge away from it
    float lit = 1.0f;
    if (( is_east && off_side < 0) || (!is_east && off_side > 0)) lit *= 1.0f - shade_side;
    if (( is_top  && off_up   < 0) || (!is_top  && off_up   > 0)) lit *= 1.0f - shade_up;

    c->flicker[i] = ou_step(c->flicker[i], FLICKER_TAU_S, flick, dt);
    float target = sun_lux * (DIFFUSE_FRACTION + (1 - DIFFUSE_FRACTION) * direct * lit) * (1 + c->flicker[i]);
    if (target < 0.01f) target = 0.01f;

    // 4. LDR lag, then 5. electrical output
    c->lux[i] += (target - c->lux[i]) * dt / (target > c->lux[i] ? LDR_TAU_RISE_S : LDR_TAU_FALL_S);
    pin_dac_write(c->pin_ldr[i], lux_to_volts(c->lux[i]));
  }

  if (++c->tick % DRAW_EVERY == 0) draw(c, c->sun_el > 0 ? 1.0f - cover * cloudiness : 0.1f);
  if (c->tick % 1000 == 0) {
    float err = acosf(clampf(sn, -1, 1)) / DEG;
    printf("sun az=%6.1f el=%5.1f | panel az=%6.1f el=%5.1f | pointing error=%5.1f deg\n",
           c->sun_az, c->sun_el, pan_az, tilt_el, err);
  }
}

void chip_init(void) {
  chip_t *c = calloc(1, sizeof(chip_t));
  const char *ldr_names[N_LDR] = { "TOP_E", "TOP_W", "BOT_E", "BOT_W" };

  c->pin_pan  = pin_init("PAN", INPUT);
  c->pin_tilt = pin_init("TILT", INPUT);
  for (int i = 0; i < N_LDR; i++) c->pin_ldr[i] = pin_init(ldr_names[i], ANALOG);

  c->attr_day     = attr_init_float("dayLength", 0);
  c->attr_lat     = attr_init_float("latitude", 45);
  c->attr_decl    = attr_init_float("declination", 0);
  c->attr_az      = attr_init_float("sunAzimuth", 30);
  c->attr_el      = attr_init_float("sunElevation", 40);
  c->attr_lux     = attr_init_float("sunLux", 400);
  c->attr_cloud   = attr_init_float("cloudCover", 0);
  c->attr_flicker = attr_init_float("reflections", 0);

  c->pan_cmd = c->pan_deg = 90;     // facing south
  c->tilt_cmd = c->tilt_deg = 45;   // halfway up
  for (int i = 0; i < N_LDR; i++) c->lux[i] = 400;

  const pin_watch_config_t watch = { .user_data = c, .edge = BOTH, .pin_change = on_pwm_edge };
  pin_watch(c->pin_pan, &watch);
  pin_watch(c->pin_tilt, &watch);

  c->fb = framebuffer_init(&c->fb_w, &c->fb_h);
  c->pixels = malloc(c->fb_w * c->fb_h * 4);

  const timer_config_t timer = { .user_data = c, .callback = on_tick };
  timer_start(timer_init(&timer), TICK_US, true);

  printf("Sun + Sensor Head (dual axis) ready\n");
}
