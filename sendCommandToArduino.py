import serial
import time
import csv
import datetime

# --- 設定 ---
COM_PORT = 'COM18'   # Arduinoのポート
BAUD_RATE = 460800   # ArduinoのSerial.beginの値と合わせてください
OUTPUT_FILE = 'vesc_imu_log.csv'

def main():
    try:
        ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=1)
        print(f"{COM_PORT} に接続しました。")
    except serial.serialutil.SerialException:
        print("ポートが見つかりません。")
        return

    time.sleep(2) # Arduinoのリセット待ち

    with open(OUTPUT_FILE, 'a', newline='') as f:
        writer = csv.writer(f)
        
        # ヘッダーを書き込む
        headers = ['Time', 'Current', 'AcX', 'AcY', 'AcZ', 'GyX', 'GyY', 'GyZ', 'Freq']
        writer.writerow(headers)
        
        print(f"計測を開始します... データ保存先: {OUTPUT_FILE}")
        print("停止は Ctrl+C")
        
        # 1. 開始コマンド送信
        ser.write(b's')

        try:
            while True:
                if ser.in_waiting > 0:
                    try:
                        # Arduinoからの行を読み取る
                        line = ser.readline().decode('utf-8').strip()
                        
                        # 空行は無視
                        if not line:
                            continue

                        # カンマで分割してリストにする
                        parts = line.split(',')
                        
                        # データの個数チェック (電流1 + IMU6 + 周波数1 = 8個以上あるか)
                        if len(parts) >= 8:
                            try:
                                # 数値として正しいか軽くチェック（最初の電流値がfloat変換できるか）
                                float(parts[0])

                                now = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
                                
                                # ログ用データ作成: [時刻] + [受信したデータのリスト]
                                log_data = [now] + parts
                                
                                # コンソール表示 (整形して表示)
                                print(f"{now} -> Cur:{parts[0]}A, Freq:{parts[-1]}Hz")
                                
                                # CSVに記録
                                writer.writerow(log_data)
                                
                            except ValueError:
                                # 数値変換エラー（通信ノイズなど）は無視
                                pass
                        
                    except UnicodeDecodeError:
                        pass

        except KeyboardInterrupt:
            print("\n停止操作を受信しました。")
        
        finally:
            # 3. 終了コマンド送信
            print("モーター停止コマンドを送信中...")
            ser.write(b'e')
            time.sleep(0.5)
            ser.close()
            print("終了しました。")

if __name__ == '__main__':
    main()