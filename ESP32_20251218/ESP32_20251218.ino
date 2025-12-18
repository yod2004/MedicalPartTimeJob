/*

<配線>
UART1 RX:16 TX:17
UART2 RX:18 TX:19
I2C SDA:21 SCL:22
<速度>
UART0 115200
UART1 115200
UART2 115200
I2C   400000
*/


#include <HardwareSerial.h>
#include <Wire.h>

// --- UART設定 ---
HardwareSerial VESC1(1);
HardwareSerial VESC2(2);

// ピン定義
#define RX1_PIN 16
#define TX1_PIN 17
#define RX2_PIN 18
#define TX2_PIN 19 
const long BAUD_RATE = 115200;

// --- I2C設定 ---
const int I2C_SLAVE_ADDR = 0x08; // Arduino側で決めたアドレス

void setup() {
  Serial.begin(115200); // PC用

  // UART初期化
  VESC1.begin(BAUD_RATE, SERIAL_8N1, RX1_PIN, TX1_PIN);
  VESC2.begin(BAUD_RATE, SERIAL_8N1, RX2_PIN, TX2_PIN);

  // I2C初期化 (SDA=21, SCL=22)
  Wire.begin();
  Wire.setClock(400000); // 400kHz (Fast Mode) にして高速化

  // ヘッダー出力
  Serial.println("Time(ms),SpeedA_UART,SpeedB_UART,SpeedC_I2C,Freq(Hz)");
  delay(1000);
}

void loop() {
  static unsigned long lastTime = 0;
  unsigned long currentTime = millis();
  
  // 1. UARTから取得
  float speedA = getVescDataUART(VESC1);
  float speedB = getVescDataUART(VESC2);

  // 2. I2Cから取得
  float speedC = getVescDataI2C(I2C_SLAVE_ADDR);

  // 3. 周波数計算
  float actualFreq = 1000.0 / (currentTime - lastTime + 0.001);
  lastTime = currentTime;

  // 4. CSV出力
  Serial.printf("%lu,%.2f,%.2f,%.2f,%.1f\n", currentTime, speedA, speedB, speedC, actualFreq);
}

// --- UART取得用関数 ---
float getVescDataUART(HardwareSerial &serialPort) {
  while (serialPort.available()) serialPort.read(); // バッファクリア
  serialPort.write('r');
  
  unsigned long startWait = micros();
  while (!serialPort.available()) {
    if (micros() - startWait > 4000) return -1.0; // 4msタイムアウト
  }
  return serialPort.readStringUntil('\n').toFloat();
}

// --- I2C取得用関数 ---
float getVescDataI2C(int address) {
  // Arduinoに4バイト(floatサイズ)要求
  Wire.requestFrom(address, 4);
  
  if (Wire.available() == 4) {
    float receivedVal;
    // 4バイト読み込んでfloat変数にメモリコピー復元
    Wire.readBytes((char*)&receivedVal, 4);
    return receivedVal;
  } else {
    return -2.0; // I2Cエラー時は -2.0
  }
}