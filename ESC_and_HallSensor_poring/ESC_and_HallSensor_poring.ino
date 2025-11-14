#include <avr/io.h>

int pwmPin = 10;
int StickYPin = A0;
int StickXPin = A1;

unsigned int frq = 500; // 周波数
float duty = 0.5; // 指定したいデューティ比
float dutyMax = 0.9;
float dutyMin = 0.5;
float RPMMax = 36600;

float calcTime = 10.0;

//for HallSensor
int HallPin = 2;
unsigned long pulseCount = 0;      // 割り込みを使っていないため volatile は不要
unsigned long lastSpeedCalcTime = 0; // 最後に速度を計算した時刻
float currentSpeedHz = 0;            // 計算された速度 (Hz)
float targetRPM = 25000;

// ホールセンサーの前の状態を記憶する変数 (RISINGエッジ検出用)
int lastHallState = LOW;

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
void setDuty(float duty) {
  OCR1B = (unsigned int)(OCR1A * duty);
}

// (割り込みサービスルーチン countPulseISR は削除)

float fmap(float x, float in_min, float in_max, float out_min, float out_max){
    float x_new = (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min;
    return x_new;
}

float pid(float r, float y, float kp, float kp_div){
  float e = r - y;
  float u = (kp * e) / kp_div;
  return u;
}

void setup() {
  setupPWM(500);
  Serial.begin(9600);
  pinMode(pwmPin, OUTPUT);
  
  // ノイズ対策のため INPUT_PULLUP を推奨します
  pinMode(HallPin, INPUT_PULLUP); 

  // (attachInterrupt は削除)
  
  // センサーの初期状態を読み込む
  lastHallState = digitalRead(HallPin);
  
  lastSpeedCalcTime = millis(); // 速度計算の基準時刻を初期化

  setDuty(dutyMax);
  delay(4000);
  setDuty(dutyMin);
  delay(2000);
}

void loop() {
  // --- 0. ホールセンサーの状態監視 (ポーリング) ---
  int currentHallState = digitalRead(HallPin);
  
  // 状態が LOW から HIGH に変化した瞬間 (RISINGエッジ) を検出
  if (currentHallState == HIGH && lastHallState == LOW) {
    pulseCount++; // パルスをカウント
  }
  lastHallState = currentHallState; // 現在の状態を保存


  // --- 1. モーター制御 (Duty比の設定) ---
  float duty = fmap(analogRead(StickYPin), 0.0, 1023.0, dutyMin, dutyMax);//本来意味はないが，この文があるとRPMの精度が向上する．
  duty = constrain(dutyMin + (dutyMax - dutyMin) * targetRPM / RPMMax, dutyMin, dutyMax);
  setDuty(duty);
  
  
  // --- 2. 速度計算 (1秒ごとに行う) ---
  unsigned long currentTime = millis();
  if (currentTime - lastSpeedCalcTime >= calcTime) { // 1000ms (1秒) 経過したら
    
    // (割り込みを使っていないため、noInterrupts/interrupts は不要)
    unsigned long pulses = pulseCount; // カウント数をコピー
    pulseCount = 0;                // カウンタをリセット
    
    // 経過時間 (秒) を計算
    float elapsedTimeSec = (float)(currentTime - lastSpeedCalcTime) / 1000.0;
    
    // 速度 (パルス/秒 = Hz) を計算
    currentSpeedHz = (float)pulses / elapsedTimeSec;
    
    lastSpeedCalcTime = currentTime; // 最後の計算時刻を更新
    
    
    // // --- 3. 結果をシリアルに出力 ---
    // Serial.print("Duty: ");
    // Serial.print(duty);
    // Serial.print("  |  Speed (RPM): ");
    // Serial.print(currentSpeedHz * 60);
    // Serial.print("  |  Speed (Hz): ");
    // Serial.println(currentSpeedHz);

    // duty = constrain(dutyMin + pid(targetRPM, currentSpeedHz * 60, 1000, 10000000), dutyMin, dutyMax);
    // setDuty(duty);
  }
}