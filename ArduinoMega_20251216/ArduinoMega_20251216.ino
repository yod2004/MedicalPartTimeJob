// #include <SoftwareSerial.h>
#include <avr/io.h>

void change_freq1(int divide){
  TCCR1B = (TCCR1B & 0b11111000) | divide;
}

// SoftwareSerial vescSerial(8, 9); // RX, TX

int pwmPin = 11;

float duty = 0.5; 
float dutyMax = 0.9;
float dutyMin = 0.14;

float maxRPM = 60000;
float minRPM = 0000;
float targetRPM = 0;

float fmap(float val, float val_min, float val_max, float res_min, float res_max){
  return res_min + (res_max - res_min) * (val - val_min) / (val_max - val_min);
}

void rotate(int RPM){
  int value = int(fmap(RPM, minRPM, maxRPM, 255*dutyMin, 255*dutyMax));
  analogWrite(pwmPin, value);// value:0~255
}


// VESCバッファ
uint8_t rx_buffer[256]; 
const uint8_t COMM_GET_VALUES = 4;

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

bool isRunning = false;

void setup() {
    change_freq1(4);//490Hz->122.5Hz
    Serial.begin(460800);
    Serial2.begin(115200);

    Serial.println("Starting...");

    // setupPWM(100);
    pinMode(pwmPin, OUTPUT);
    targetRPM = 5000;
}

void loop() {
    // --- コマンド受信処理 ---
    if (Serial.available() > 0) {
        char command = Serial.read();
        if (command == 's') {
            isRunning = true;
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
        
        // データをバッファに溜める
        while (millis() - startTime < 50) {
            if (Serial2.available()) {
                uint8_t c = Serial2.read();

                if (!packetStarted) {
                    if (c == 0x02) { // スタートバイト発見
                        packetStarted = true;
                        byteIndex = 0;
                    }
                } else {
                    rx_buffer[byteIndex++] = c; 
                    if (byteIndex >= sizeof(rx_buffer)) break;
                    if (byteIndex > 0) {
                        uint8_t payloadLen = rx_buffer[0];
                        // 必要なバイト数 = Len + CRC(2) + End(1)
                        // byteIndex は個数なので、これと一致すれば受信完了
                        if (byteIndex >= payloadLen + 3) {
                             break; // これで待ち時間をキャンセルして即次へ進む
                        }
                    } 
                }
            }
        }

        // --- ここから修正：CRCチェックを追加 ---
        // データがある程度たまっているか確認
        if (byteIndex > 5) {
            int payloadLen = rx_buffer[0]; // 最初のバイトは「長さ」

            // 最後まで受信できているか確認 (長さバイト + 本体 + CRC2バイト + 終了バイト)
            // byteIndexは 終了バイト(0x03)の手前まで入っているはず
            if (byteIndex >= payloadLen + 3) {
                
                // 受信したCRCの値を取り出す
                uint16_t receivedCrc = (rx_buffer[payloadLen + 1] << 8) | rx_buffer[payloadLen + 2];
                
                // 自分で計算してみる (rx_buffer[1] から payloadLenバイト分)
                uint16_t calculatedCrc = crc16(&rx_buffer[1], payloadLen);

                // 計算が合致したら、正しいデータとみなす！
                if (receivedCrc == calculatedCrc) {
                    int32_t ind = 1; 
                    if (rx_buffer[ind++] == COMM_GET_VALUES) {
                        // 読み飛ばし
                        buffer_get_int16(rx_buffer, &ind); // Temp FET
                        buffer_get_int16(rx_buffer, &ind); // Temp Motor
                        
                        // 電流値取得
                        float currentMotor = buffer_get_int32(rx_buffer, &ind) / 100.0;
                        
                        // Pythonへ送信 (小数点第2位まで送ると良いでしょう)
                        Serial.println(currentMotor);
                    }
                }
            }
        }
        // ----------------------------------------

        // setRPM(targetRPM);
        rotate(targetRPM);
        if(targetRPM > maxRPM){
            targetRPM = 0;
        }
        
        // 連続送信しすぎると詰まるので少し待つ
        // delay(1);
    }
}