#include <SoftwareSerial.h>
#include <avr/io.h>

SoftwareSerial vescSerial(8, 9); // RX, TX

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

// VESCからの応答パケット用バッファ
uint8_t rx_buffer[256]; 

// --- VESC コマンドID ---
const uint8_t COMM_GET_VALUES = 4;

// --- CRC16 計算関数 (変更なし) ---
unsigned short crc16(unsigned char *buf, unsigned int len) {
    unsigned int i;
    unsigned short cksum = 0;
    for (i = 0; i < len; i++) {
        cksum = crc16_round(cksum, buf[i]);
    }
    return cksum;
}

unsigned short crc16_round(unsigned short crc, unsigned char data) {
    crc = (unsigned char)(crc >> 8) | (crc << 8);
    crc ^= data;
    crc ^= (unsigned char)(crc & 0xff) >> 4;
    crc ^= (crc << 8) << 4;
    crc ^= ((crc & 0xff) << 4) << 1;
    return crc;
}

// --- 数値変換関数 (変更なし) ---
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

// --- データ要求送信 (変更なし) ---
void request_vesc_values() {
    uint8_t payload[] = { COMM_GET_VALUES };
    uint8_t len = sizeof(payload);
    uint16_t crc = crc16(payload, len);

    vescSerial.write(0x02);
    vescSerial.write(len);
    vescSerial.write(payload, len);
    vescSerial.write((uint8_t)(crc >> 8));
    vescSerial.write((uint8_t)(crc & 0xFF));
    vescSerial.write(0x03);
}

void setup() {
    Serial.begin(9600);
    
    // VESCとの通信開始 (8番, 9番ピンを使用)
    vescSerial.begin(9600); 
    
    Serial.println("Starting VESC Monitor on Pins 8/9...");

    setupPWM(100);//100Hz
    pinMode(pwmPin, OUTPUT);
    targetRPM = 5000;
}

void loop() {
    request_vesc_values();

    unsigned long startTime = millis();
    int byteIndex = 0;
    bool packetStarted = false;
    
    while (millis() - startTime < 100) {
        if (vescSerial.available()) {
            uint8_t c = vescSerial.read();

            if (!packetStarted) {
                if (c == 0x02) {
                    packetStarted = true;
                    byteIndex = 0;
                }
            } else {
                rx_buffer[byteIndex++] = c;
                if (byteIndex >= sizeof(rx_buffer)) break; 
            }
        }
    }

    if (byteIndex > 10) {
        int32_t ind = 1; 

        if (rx_buffer[ind++] == COMM_GET_VALUES) {
            float tempFET = buffer_get_int16(rx_buffer, &ind) / 10.0;
            float tempMotor = buffer_get_int16(rx_buffer, &ind) / 10.0;
            float currentMotor = buffer_get_int32(rx_buffer, &ind) / 100.0;
            float currentInput = buffer_get_int32(rx_buffer, &ind) / 100.0;
            buffer_get_int32(rx_buffer, &ind); // ID
            buffer_get_int32(rx_buffer, &ind); // IQ
            float duty = buffer_get_int16(rx_buffer, &ind) / 1000.0;
            float rpm = buffer_get_int32(rx_buffer, &ind);
            float voltage = buffer_get_int16(rx_buffer, &ind) / 10.0;

            Serial.print("Volt: "); Serial.print(voltage); 
            Serial.print(" V | RPM: "); Serial.print(rpm);
            Serial.print(" | Curr: "); Serial.println(currentMotor);
        }
    }

    setRPM(targetRPM);
    if(targetRPM > maxRPM){
      targetRPM = 0;
    }
    delay(100);
}