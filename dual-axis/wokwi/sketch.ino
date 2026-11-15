// Dual axis solar tracker: four photoresistors -> Arduino -> pan and tilt servos
// Runs unchanged on a real Arduino Uno.
//
// Sensor layout, looking at the panel face (a cross-shaped wall separates them):
//
//        TOP_W | TOP_E
//       -------+-------
//        BOT_W | BOT_E
//
// Each axis is controlled on its own:
//   pan  error = (east pair)  - (west pair)    -> turn east or west
//   tilt error = (top pair)   - (bottom pair)  -> tilt up or down

#include <Servo.h>

// ---------- pins ----------
const int LDR_TOP_E = A0;
const int LDR_TOP_W = A1;
const int LDR_BOT_E = A2;
const int LDR_BOT_W = A3;
const int PAN_PIN   = 9;
const int TILT_PIN  = 10;

// More light = lower voltage on the sensor, so flip it: bigger number = brighter.
const bool BRIGHTER_IS_LOWER = true;

// ---------- control settings ----------
const int  STEP_DEG   = 1;
const int  LOOP_MS    = 30;
const int  THRESHOLD  = 10;     // raw logic: minimum difference before moving (ADC counts)

const bool USE_FILTER = false;  // false = raw threshold, true = moving average + deadband
const int  WINDOW     = 20;     // moving average length (20 readings = 0.6 s)
const int  DEADBAND   = 40;     // filtered logic: minimum averaged difference before moving

const int  PAN_MIN = 0,  PAN_MAX = 180;   // 90 = facing south, 180 = facing east
const int  TILT_MIN = 0, TILT_MAX = 90;   // 0 = facing the horizon, 90 = facing straight up

// ---------- one axis of control ----------
// A struct groups the variables for one axis, like a small Python class with no methods.
struct Axis {
  Servo servo;
  int angle;
  int minAngle, maxAngle;
  int history[WINDOW];
  long historySum;
  int historyIndex, historyCount;
  int lastDirection;
  long moves, reversals;
};

Axis pan;
Axis tilt;

int readBrightness(int pin) {
  int raw = analogRead(pin);
  return BRIGHTER_IS_LOWER ? 1023 - raw : raw;
}

int movingAverage(Axis &a, int newValue) {   // "Axis &a" passes the axis itself, not a copy
  a.historySum -= a.history[a.historyIndex];
  a.history[a.historyIndex] = newValue;
  a.historySum += newValue;
  a.historyIndex = (a.historyIndex + 1) % WINDOW;
  if (a.historyCount < WINDOW) a.historyCount++;
  return a.historySum / a.historyCount;
}

// Runs the same threshold logic as the single axis version, for one axis.
// Returns the signal it compared, for logging.
int controlAxis(Axis &a, int error) {
  int signal = error;
  int limit  = THRESHOLD;
  if (USE_FILTER) {
    signal = movingAverage(a, error);
    limit  = DEADBAND;
  }

  int direction = 0;
  if (signal > limit)       direction = +1;
  else if (signal < -limit) direction = -1;

  if (direction != 0) {
    a.angle = constrain(a.angle + direction * STEP_DEG, a.minAngle, a.maxAngle);
    a.servo.write(a.angle);
    a.moves++;
    if (a.lastDirection != 0 && direction != a.lastDirection) a.reversals++;
    a.lastDirection = direction;
  }
  return signal;
}

void setupAxis(Axis &a, int pin, int start, int minAngle, int maxAngle) {
  a.angle = start;
  a.minAngle = minAngle;
  a.maxAngle = maxAngle;
  a.historySum = 0;
  a.historyIndex = 0;
  a.historyCount = 0;
  a.lastDirection = 0;
  a.moves = 0;
  a.reversals = 0;
  for (int i = 0; i < WINDOW; i++) a.history[i] = 0;
  a.servo.attach(pin);
  a.servo.write(start);
}

void setup() {
  Serial.begin(115200);
  setupAxis(pan,  PAN_PIN,  90, PAN_MIN,  PAN_MAX);
  setupAxis(tilt, TILT_PIN, 45, TILT_MIN, TILT_MAX);
  Serial.println(USE_FILTER ? "Mode: moving average + deadband" : "Mode: raw threshold");
}

void loop() {
  // 1. INPUT
  int topE = readBrightness(LDR_TOP_E);
  int topW = readBrightness(LDR_TOP_W);
  int botE = readBrightness(LDR_BOT_E);
  int botW = readBrightness(LDR_BOT_W);

  // 2. LOGIC: average each pair, then compare the pairs
  int panError  = (topE + botE) / 2 - (topW + botW) / 2;   // > 0: east side brighter
  int tiltError = (topE + topW) / 2 - (botE + botW) / 2;   // > 0: top edge brighter

  // 3. OUTPUT (inside controlAxis)
  int panSignal  = controlAxis(pan,  panError);
  int tiltSignal = controlAxis(tilt, tiltError);

  Serial.print("panErr:");    Serial.print(panSignal);
  Serial.print(" tiltErr:");  Serial.print(tiltSignal);
  Serial.print(" pan:");      Serial.print(pan.angle);
  Serial.print(" tilt:");     Serial.print(tilt.angle);
  Serial.print(" panRev:");   Serial.print(pan.reversals);
  Serial.print(" tiltRev:");  Serial.println(tilt.reversals);

  delay(LOOP_MS);
}
