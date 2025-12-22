#include <avr/io.h>
#include <Wire.h> 

// --- MPU-6050設定 ---
const int MPU_addr = 0x68;
int16_t AcX, AcY, AcZ, Tmp, GyX, GyY, GyZ;

// --- PWM設定 ---
int pwmPin = 11;

void change_freq1(int divide){
  TCCR1B = (TCCR1B & 0b11111000) | divide;
}

float duty = 0.5; 
float dutyMax = 0.9;
float dutyMin = 0.1;

float maxRPM = 60000;
float minRPM = 0;
float targetRPM = 0;

float fmap(float val, float val_min, float val_max, float res_min, float res_max){
  return res_min + (res_max - res_min) * (val - val_min) / (val_max - val_min);
}

void rotate(int RPM){
  int value = int(fmap(RPM, minRPM, maxRPM, 255.0 * dutyMin, 255.0 * dutyMax));
  analogWrite(pwmPin, value);
}

// VESCバッファ
uint8_t rx_buffer[256]; 
const uint8_t COMM_GET_VALUES = 4;

// --- CRC計算 ---
unsigned short crc16_round(unsigned short crc, unsigned char data) {
    crc = (unsigned char)(crc >> 8) | (crc << 8);
    crc ^= data;
    crc ^= (unsigned char)(crc & 0xff) >> 4;
    crc ^= (crc << 8) << 4;
    crc ^= ((crc & 0xff) << 4) << 1;
    return crc;
}
unsigned short crc16(unsigned char *buf, unsigned int len) {
    unsigned int i;
    unsigned short cksum = 0;
    for (i = 0; i < len; i++) {
        cksum = crc16_round(cksum, buf[i]);
    }
    return cksum;
}

// --- バッファ読み取り ---
int16_t buffer_get_int16(const uint8_t *buffer, int32_t *index) {
    int16_t res = ((uint16_t)buffer[*index]) << 8 | ((uint16_t)buffer[*index + 1]);
    *index += 2;
    return res;
}
int32_t buffer_get_int32(const uint8_t *buffer, int32_t *index) {
    int32_t res = ((uint32_t)buffer[*index]) << 24 |
                  ((uint32_t)buffer[*index + 1]) << 16 |
                  ((uint32_t)buffer[*index + 2]) << 8 |
                  ((uint32_t)buffer[*index + 3]);
    *index += 4;
    return res;
}

void request_vesc_values() {
    uint8_t payload[] = { COMM_GET_VALUES };
    uint8_t len = sizeof(payload);
    uint16_t crc = crc16(payload, len);

    Serial2.write(0x02);
    Serial2.write(len);
    Serial2.write(payload, len);
    Serial2.write((uint8_t)(crc >> 8));
    Serial2.write((uint8_t)(crc & 0xFF));
    Serial2.write(0x03);
}

// --- MPU-6050読み取り関数 ---
void readIMU() {
  Wire.beginTransmission(MPU_addr);
  Wire.write(0x3B); 
  Wire.endTransmission(false);
  Wire.requestFrom(MPU_addr, 14, true); 
  
  if (Wire.available() >= 14) {
      AcX = Wire.read()<<8 | Wire.read();  
      AcY = Wire.read()<<8 | Wire.read();  
      AcZ = Wire.read()<<8 | Wire.read();  
      Tmp = Wire.read()<<8 | Wire.read();  
      GyX = Wire.read()<<8 | Wire.read();  
      GyY = Wire.read()<<8 | Wire.read();  
      GyZ = Wire.read()<<8 | Wire.read();  
  }
}

bool isRunning = false;
unsigned long lastTime = 0; // 周波数計算用

void setup() {
    change_freq1(4); 
    
    Serial.begin(460800); 
    Serial2.begin(115200);

    Wire.begin();
    Wire.setClock(400000); 
    Wire.beginTransmission(MPU_addr);
    Wire.write(0x6B);  
    Wire.write(0);     
    Wire.endTransmission(true);

    Serial.println("Starting...");

    pinMode(pwmPin, OUTPUT);
    targetRPM = 5000;
}

void loop() {
    if (Serial.available() > 0) {
        char command = Serial.read();
        if (command == 's') {
            isRunning = true;
            lastTime = millis(); // スタート時に時間をリセット
        } else if (command == 'e') {
            isRunning = false; 
            rotate(0);
        }
    }

    if(isRunning){
        request_vesc_values();

        unsigned long startTime = millis();
        int byteIndex = 0;
        bool packetStarted = false;
        
        while (millis() - startTime < 50) {
            if (Serial2.available()) {
                uint8_t c = Serial2.read();

                if (!packetStarted) {
                    if (c == 0x02) { 
                        packetStarted = true;
                        byteIndex = 0;
                    }
                } else {
                    rx_buffer[byteIndex++] = c; 
                    if (byteIndex >= sizeof(rx_buffer)) break;
                    
                    if (byteIndex > 0) {
                        uint8_t payloadLen = rx_buffer[0];
                        if (byteIndex >= payloadLen + 3) {
                             break; 
                        }
                    } 
                }
            }
        }

        // --- データ解析 ---
        if (byteIndex > 5) {
            int payloadLen = rx_buffer[0]; 

            if (byteIndex >= payloadLen + 3) {
                uint16_t receivedCrc = (rx_buffer[payloadLen + 1] << 8) | rx_buffer[payloadLen + 2];
                uint16_t calculatedCrc = crc16(&rx_buffer[1], payloadLen);

                if (receivedCrc == calculatedCrc) {
                    int32_t ind = 1; 
                    if (rx_buffer[ind++] == COMM_GET_VALUES) {
                        buffer_get_int16(rx_buffer, &ind); 
                        buffer_get_int16(rx_buffer, &ind); 
                        
                        // 1. 電流値
                        float currentMotor = buffer_get_int32(rx_buffer, &ind) / 100.0;
                        
                        // 2. IMU
                        readIMU();

                        // 3. 周波数計算
                        unsigned long currentTime = millis();
                        float actualFreq = 1000.0 / (currentTime - lastTime + 0.001); // 0割り防止
                        lastTime = currentTime;

                        // 4. 一括送信
                        Serial.print(currentMotor);Serial.print(",");
                        Serial.print(AcX); Serial.print(",");
                        Serial.print(AcY); Serial.print(",");
                        Serial.print(AcZ); Serial.print(",");
                        Serial.print(GyX); Serial.print(",");
                        Serial.print(GyY); Serial.print(",");
                        Serial.print(GyZ); Serial.print(",");
                        Serial.println(actualFreq); // 最後に周波数を追加
                    }
                }
            }
        }
        
        rotate(targetRPM);
        if(targetRPM > maxRPM){
            targetRPM = 0;
        }
    }
}