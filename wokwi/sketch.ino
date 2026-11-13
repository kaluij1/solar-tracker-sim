// Single axis solar tracker: two photoresistors -> Arduino -> servo
// Runs unchanged on a real Arduino Uno.

#include <Servo.h>

// ---------- pins ----------
const int LDR_EAST_PIN = A0;
const int LDR_WEST_PIN = A1;
const int SERVO_PIN    = 9;

// ---------- sensor wiring ----------
// On the photoresistor module, more light = lower voltage on AO.
// Flipping it makes "bigger number = brighter", which is easier to reason about.
// Check in step 4: if east goes DOWN when you raise its lux, set this to false.
const bool BRIGHTER_IS_LOWER = true;

// ---------- control settings ----------
const int  STEP_DEG   = 1;      // servo step per command
const int  LOOP_MS    = 30;     // loop period (about 33 loops per second)
const int  THRESHOLD  = 10;     // original logic: minimum difference before moving (ADC counts)

const bool USE_FILTER = false;  // false = original logic, true = moving average + deadband
const int  WINDOW     = 20;     // moving average length (20 readings = 0.6 s)
const int  DEADBAND   = 40;     // filtered logic: minimum averaged difference before moving

// ---------- state ----------
Servo servo;
int angle = 90;                 // start pointing straight up (servo range 0 to 180)

int  history[WINDOW];
long historySum = 0;
int  historyIndex = 0;
int  historyCount = 0;

int  lastDirection = 0;
long moves = 0;
long reversals = 0;

int readBrightness(int pin) {
  int raw = analogRead(pin);              // 0 to 1023 from the 10-bit ADC
  return BRIGHTER_IS_LOWER ? 1023 - raw : raw;
}

int movingAverage(int newValue) {
  historySum -= history[historyIndex];    // drop the oldest reading
  history[historyIndex] = newValue;       // store the newest
  historySum += newValue;
  historyIndex = (historyIndex + 1) % WINDOW;
  if (historyCount < WINDOW) historyCount++;
  return historySum / historyCount;
}

void setup() {
  Serial.begin(115200);
  servo.attach(SERVO_PIN);
  servo.write(angle);
  Serial.println(USE_FILTER ? "Mode: moving average + deadband" : "Mode: raw threshold");
}

void loop() {
  // 1. INPUT
  int east  = readBrightness(LDR_EAST_PIN);
  int west  = readBrightness(LDR_WEST_PIN);
  int error = east - west;                 // > 0 means east is brighter

  // 2. LOGIC
  int signal = error;
  int limit  = THRESHOLD;
  if (USE_FILTER) {
    signal = movingAverage(error);
    limit  = DEADBAND;
  }

  int direction = 0;
  if (signal > limit)       direction = +1;   // turn east
  else if (signal < -limit) direction = -1;   // turn west
  // otherwise hold still

  // 3. OUTPUT
  if (direction != 0) {
    angle = constrain(angle + direction * STEP_DEG, 0, 180);
    servo.write(angle);                       // sends a PWM pulse width to the servo
    moves++;
    if (lastDirection != 0 && direction != lastDirection) reversals++;
    lastDirection = direction;
  }

  // log for the Serial Monitor / Serial Plotter
  Serial.print("east:");      Serial.print(east);
  Serial.print(" west:");     Serial.print(west);
  Serial.print(" error:");    Serial.print(error);
  Serial.print(" signal:");   Serial.print(signal);
  Serial.print(" angle:");    Serial.print(angle);
  Serial.print(" moves:");    Serial.print(moves);
  Serial.print(" reversals:"); Serial.println(reversals);

  delay(LOOP_MS);
}
