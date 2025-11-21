/*
   Smart Plant System
   - OLED happy face (shifted right)
   - Fake corner data on OLED
   - Reads A0..A3, prints % to Serial every ~1s
   - Pump runs 3s every 3min automatically or when commanded
   - Buzzer active during pump
   - Serial commands:
        CMD:STATUS → sends live sensor readings
        CMD:WATER  → activates pump (manual mode)
*/

#include <U8g2lib.h>
#include <Wire.h>
#include <math.h>

/* ---------------- OLED ---------------- */
U8G2_SSD1306_128X64_NONAME_F_HW_I2C oled(U8G2_R0, U8X8_PIN_NONE);

/* -------------- Pins ------------------ */
const int PIN_PUMP   = 11;   // MOSFET/relay (active HIGH)
const int PIN_BUZZER = 8;    // active buzzer

/* ----- UI horizontal shift (move pixels right) ----- */
const int X_SHIFT = 8;

/* -------------- Pump timing ---------------- */
const unsigned long PUMP_ON_MS     = 3000;      // 3 seconds
const unsigned long PUMP_PERIOD_MS = 180000;    // 3 minutes
bool pumpOn = false;
unsigned long pumpStart = 0;
unsigned long lastPumpAuto = 0;

/* -------------- Serial command ------------- */
String rx;

/* -------------- Helpers ------------------- */
typedef struct { float x, y; } V2;
float lerpf(float a, float b, float t) { return a + (b - a) * t; }
V2 lerpV(V2 a, V2 b, float t) { V2 r = { lerpf(a.x, b.x, t), lerpf(a.y, b.y, t) }; return r; }
V2 cubic(V2 p0, V2 p1, V2 p2, V2 p3, float t) {
  float u = 1.0f - t, u2 = u * u, u3 = u2 * u, t2 = t * t, t3 = t2 * t;
  V2 r = { u3 * p0.x + 3 * u2 * t * p1.x + 3 * u * t2 * p2.x + t3 * p3.x,
           u3 * p0.y + 3 * u2 * t * p1.y + 3 * u * t2 * p2.y + t3 * p3.y };
  return r;
}
int clampInt(int x, int a, int b) { if (x < a) return a; if (x > b) return b; return x; }
int mapToPercent(int raw) { long p = (long)raw * 100L / 1023L; if (p < 0) p = 0; if (p > 100) p = 100; return (int)p; }

/* -------------- Emoji geometry -------------- */
const int CX = 64 + X_SHIFT, CY = 32, R = 26;
const int E_OFF_X = 10, E_OFF_Y = 8, E_R = 3;
const int M_W = 36, M_Y = CY + 8;

void drawMouthClippedHappy(int cx, int cy, int radius, int mouthW, int mouthY) {
  float mood01 = 1.0f; // happy form
  V2 L = { (float)(cx - mouthW / 2), (float)mouthY };
  V2 Rr = { (float)(cx + mouthW / 2), (float)mouthY };

  V2 u0 = { L.x, L.y - 2 }, u1 = { (float)(cx - mouthW * 0.20f), (float)(mouthY - 2) },
     u2 = { (float)(cx + mouthW * 0.20f), (float)(mouthY - 2) }, u3 = { Rr.x, Rr.y - 2 };
  V2 l0 = { L.x, L.y - 2 }, l1 = { (float)(cx - mouthW * 0.24f), (float)(mouthY + 7) },
     l2 = { (float)(cx + mouthW * 0.24f), (float)(mouthY + 7) }, l3 = { Rr.x, Rr.y - 2 };

  const int STEPS = 44;
  for (int i = 0; i <= STEPS; i++) {
    float t = (float)i / STEPS;
    V2 up = cubic(u0, u1, u2, u3, t);
    V2 lo = cubic(l0, l1, l2, l3, t);
    int x = (int)round((up.x + lo.x) * 0.5f);
    int yu = (int)round(up.y);
    int yl = (int)round(lo.y);
    if (yl < yu) { int tmp = yu; yu = yl; yl = tmp; }

    int dx = x - cx; if (abs(dx) > radius) continue;
    float yReach = sqrtf((float)(radius * radius - dx * dx));
    int yTop = (int)ceil(cy - yReach);
    int yBot = (int)floor(cy + yReach);
    int y1 = max(yu, yTop), y2 = min(yl, yBot);
    if (y2 >= y1) { oled.setDrawColor(0); oled.drawLine(x, y1, x, y2); }
  }
}

void drawHappyEmoji() {
  oled.setDrawColor(1);
  oled.drawDisc(CX, CY, R);
  oled.setDrawColor(0);
  oled.drawDisc(CX - E_OFF_X, CY - E_OFF_Y, E_R);
  oled.drawDisc(CX + E_OFF_X, CY - E_OFF_Y, E_R);
  drawMouthClippedHappy(CX, CY, R, M_W, M_Y);
  oled.setDrawColor(1);
}

/* -------------- Fake data (corner UI) -------------- */
void fakeData(int &tPct, int &lPct, int &sPct, int &wPct) {
  float tt = millis() / 1000.0f;
  tPct = clampInt((int)(55 + 10 * sin(tt * 0.6f)), 0, 100);
  lPct = clampInt((int)(60 + 20 * sin(tt * 0.4f + 1)), 0, 100);
  sPct = clampInt((int)(65 + 15 * sin(tt * 0.5f + 2)), 0, 100);
  wPct = clampInt((int)(70 + 8 * sin(tt * 0.3f + 3)), 0, 100);
}

/* -------------- UI drawing ---------------- */
void drawScreen() {
  oled.clearBuffer();
  drawHappyEmoji();

  int t, l, s, w; fakeData(t, l, s, w);
  oled.setFont(u8g2_font_5x7_tr);
  char buf[20];
  int x = 0 + X_SHIFT;

  oled.drawStr(x, 8, "FAKE");
  sprintf(buf, "T:%d%%", t); oled.drawStr(x, 18, buf);
  sprintf(buf, "L:%d%%", l); oled.drawStr(x, 28, buf);
  sprintf(buf, "S:%d%%", s); oled.drawStr(x, 38, buf);
  sprintf(buf, "W:%d%%", w); oled.drawStr(x, 48, buf);

  if (pumpOn) oled.drawStr(96 + X_SHIFT / 2, 60, "PUMP");
  oled.sendBuffer();
}

/* -------------- Pump control --------------- */
void startPump() {
  pumpOn = true;
  pumpStart = millis();
  digitalWrite(PIN_PUMP, HIGH);
  digitalWrite(PIN_BUZZER, HIGH);
}

void stopPump() {
  pumpOn = false;
  digitalWrite(PIN_PUMP, LOW);
  digitalWrite(PIN_BUZZER, LOW);
}

/* -------------- Serial handler --------------- */
void handleSerial() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (rx.length()) {
        String s = rx; s.trim(); s.toUpperCase();

        if (s == "PUMP" || s == "PUMP_ON" || s == "CMD:WATER") {
          startPump();
          Serial.println(F("ACK:PUMPING"));
        }
        else if (s == "STATUS" || s == "CMD:STATUS") {
          int a0 = analogRead(A0);
          int a1 = analogRead(A1);
          int a2 = analogRead(A2);
          int a3 = analogRead(A3);
          int p0 = mapToPercent(a0);
          int p1 = mapToPercent(a1);
          int p2 = mapToPercent(a2);
          int p3 = mapToPercent(a3);

          Serial.print(F("SENS% T=")); Serial.print(p0);
          Serial.print(F(" L=")); Serial.print(p1);
          Serial.print(F(" S=")); Serial.print(p2);
          Serial.print(F(" W=")); Serial.print(p3);
          Serial.print(F(" PUMP=")); Serial.println(pumpOn ? 1 : 0);
        }
        rx = "";
      }
    } else {
      if (rx.length() < 64) rx += c;
    }
  }
}

/* -------------- Pump timing --------------- */
void updatePumpTimers() {
  if (pumpOn && millis() - pumpStart >= PUMP_ON_MS) {
    stopPump();
    Serial.println(F("ACK:PUMP_DONE"));
  }
  if (!pumpOn && millis() - lastPumpAuto >= PUMP_PERIOD_MS) {
    lastPumpAuto = millis();
    startPump();
    Serial.println(F("ACK:PUMP_AUTO"));
  }
}

/* -------------- Sensor logging --------------- */
unsigned long lastPrint = 0;
void readAndLogSensors() {
  if (millis() - lastPrint < 1000) return;
  lastPrint = millis();

  int a0 = analogRead(A0);
  int a1 = analogRead(A1);
  int a2 = analogRead(A2);
  int a3 = analogRead(A3);
  int p0 = mapToPercent(a0);
  int p1 = mapToPercent(a1);
  int p2 = mapToPercent(a2);
  int p3 = mapToPercent(a3);

  Serial.print(F("SENS% T=")); Serial.print(p0);
  Serial.print(F(" L=")); Serial.print(p1);
  Serial.print(F(" S=")); Serial.print(p2);
  Serial.print(F(" W=")); Serial.print(p3);
  Serial.print(F(" PUMP=")); Serial.println(pumpOn ? 1 : 0);
}

/* -------------- Setup & loop --------------- */
void setup() {
  pinMode(PIN_PUMP, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);
  digitalWrite(PIN_PUMP, LOW);
  digitalWrite(PIN_BUZZER, LOW);

  Serial.begin(115200);
  oled.begin();
  lastPumpAuto = millis();
}

void loop() {
  handleSerial();
  updatePumpTimers();
  readAndLogSensors();
  drawScreen();
  delay(50);
}