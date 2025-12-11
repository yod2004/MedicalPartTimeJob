import serial
import time
import csv
import datetime

# --- 設定 ---
COM_PORT = 'COM6'   # Arduinoのポートに合わせてください
BAUD_RATE = 115200
OUTPUT_FILE = 'vesc_log.csv'

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
        print("計測を開始します... (停止は Ctrl+C)")
        
        # 1. 開始コマンド送信
        ser.write(b's')

        try:
            while True:
                if ser.in_waiting > 0:
                    try:
                        # Arduinoからの行を読み取る
                        line = ser.readline().decode('utf-8').strip()
                        
                        # 数値変換できるかトライする（小数対応）
                        try:
                            val = float(line) # これで "10.50" もOKになる
                            
                            now = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
                            print(f"{now} -> {val}") # コンソールに表示
                            writer.writerow([now, val]) # CSVに記録
                            
                        except ValueError:
                            # 数値じゃない行（エラーメッセージなど）は無視
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