#include <avr/io.h>

int pwmPin = 10;
int StickYPin = A0;
int StickXPin = A1;

unsigned int frq = 100; // 周波数
float duty = 0.5; // 指定したいデューティ比
float dutyMax = 0.9;
float dutyMin = 0.2;

double maxRPM = 60000;
double minRPM = 0000;
double targetRPM = 0;
double dduty = 0;

void setRPM(double rpm){
  dduty = dmap(targetRPM, minRPM, maxRPM, 0.31, dutyMax);
  Serial.print("duty : "); Serial.println(dduty);
  setDuty(dduty);
}

void setupPWM(int frq) {
  pinMode(pwmPin, OUTPUT);
  TCCR1A = 0b00100001;
  TCCR1B = 0b00010100; 
  OCR1A = (unsigned int)(31250 / frq);
}

/**
 * @brief PWMのDuty比を設定する
 * @param duty Duty比 (0.0 ~ 1.0)
 */
void setDuty(double duty) {
  OCR1B = (unsigned int)(OCR1A * duty);
}

float fmap(float x, float in_min, float in_max, float out_min, float out_max){
    float x_new = (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min;
    return x_new;
}

double dmap(double x, double in_min, double in_max, double out_min, double out_max){
    double x_new = (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min;
    return x_new;
}

void setup() {
  setupPWM(100);//100Hz
  pinMode(pwmPin, OUTPUT);
  Serial.begin(9600);
  targetRPM = 5000;
}

void loop() {
  // --- 1. モーター制御 (Duty比の設定) ---
  // float duty = constrain(fmap(analogRead(StickYPin), 0.0, 1023.0, dutyMin, dutyMax),dutyMin,dutyMax);
  // setDuty(duty);
  Serial.print("targetRPM : "); Serial.println(targetRPM);
  setRPM(targetRPM);
  delay(5000);
  // targetRPM += 4000;
  if(targetRPM > maxRPM){
    targetRPM = 0;
  }
  // targetRPM = -60000;
}