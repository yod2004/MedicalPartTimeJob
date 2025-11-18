// Arduino入門編㉛ INA219モジュールを使い電流・電圧の計測を行う！
// https://burariweb.info
#include <Wire.h>                      // ライブラリのインクルード
#include <Adafruit_INA219.h>
Adafruit_INA219 ina219;                // INA219オブジェクトの生成(アドレス0x40)
void setup(void)
{
  Serial.begin(115200);                // シリアル通信の開始
  ina219.begin();                      // INA219との通信を開始(初期化)
  // ina219.setCalibration_16V_400mA();   // 測定レンジの設定
//ina219.setCalibration_32V_1A();
ina219.setCalibration_32V_2A();
}
void loop(void)
{
  float shuntvoltage = 0;
  float busvoltage = 0;
  float current_mA = 0;
  float loadvoltage = 0;
  float power_mW = 0;
  shuntvoltage = ina219.getShuntVoltage_mV();        // シャント抵抗間の電圧計測
  busvoltage = ina219.getBusVoltage_V();             // 接続した回路の電圧計測
  current_mA = ina219.getCurrent_mA();               // 電流の計測
  power_mW = ina219.getPower_mW();                   // 電力の計測
  loadvoltage = busvoltage + (shuntvoltage / 1000);  // 負荷電圧の計算
  Serial.print("Bus Voltage:   "); Serial.print(busvoltage); Serial.print(" V ");
  Serial.print("Shunt Voltage: "); Serial.print(shuntvoltage); Serial.print(" mV ");
  Serial.print("Load Voltage:  "); Serial.print(loadvoltage); Serial.print(" V ");
  Serial.print("Current:       "); Serial.print(current_mA); Serial.print(" mA ");
  Serial.print("Power:         "); Serial.print(power_mW); Serial.println(" mW ");
  Serial.println("");
  // delay(200);
}