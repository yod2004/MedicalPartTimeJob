import bcapclient
import serial
import time
import csv
import datetime
import threading

# --- 設定: Arduino / ログ ---
COM_PORT = 'COM18'
BAUD_RATE = 460800
OUTPUT_FILE = 'vesc_imu_log.csv'

# --- 設定: ロボット (b-CAP) ---
HOST = "10.1.1.190"
PORT = 5007
TIMEOUT = 2000
PROVIDER = "CaoProv.DENSO.VRC9"
MACHINE = "localhost"

# ログ記録を停止するためのフラグ
stop_event = threading.Event()

def serial_logger_task():
    """
    バックグラウンドで実行されるシリアル通信・ログ保存用関数
    """
    try:
        ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=1)
        print(f"[Serial] {COM_PORT} に接続しました。")
    except serial.serialutil.SerialException:
        print("[Serial] ポートが見つかりません。ログ記録をスキップします。")
        return

    time.sleep(2)  # Arduinoのリセット待ち

    with open(OUTPUT_FILE, 'a', newline='') as f:
        writer = csv.writer(f)
        headers = ['Time', 'Current', 'AcX', 'AcY', 'AcZ', 'GyX', 'GyY', 'GyZ', 'Freq']
        writer.writerow(headers)
        
        print(f"[Serial] 計測を開始します... 保存先: {OUTPUT_FILE}")
        ser.write(b's') # 開始コマンド

        try:
            # stop_eventがセットされるまでループし続ける
            while not stop_event.is_set():
                if ser.in_waiting > 0:
                    try:
                        line = ser.readline().decode('utf-8').strip()
                        if not line: continue

                        parts = line.split(',')
                        if len(parts) >= 8:
                            try:
                                float(parts[0]) # 数値チェック
                                now = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
                                log_data = [now] + parts
                                print(f"[Serial] {now} -> Cur:{parts[0]}A, Freq:{parts[-1]}Hz")
                                writer.writerow(log_data)
                            except ValueError:
                                pass
                    except UnicodeDecodeError:
                        pass
        finally:
            print("[Serial] 停止コマンドを送信中...")
            ser.write(b'e') # 終了コマンド
            time.sleep(0.5)
            ser.close()
            print("[Serial] 接続を閉じました。")

def main():
    # 1. ログ記録用スレッドの準備と開始
    # -------------------------------------------------
    logger_thread = threading.Thread(target=serial_logger_task)
    logger_thread.start()
    
    # ログ記録が安定して始まるまで少し待つ
    time.sleep(3)

    # 2. ロボットの制御 (メインスレッド)
    # -------------------------------------------------
    try:
        print("[Robot] Connecting to b-CAP...")
        m_bcapclient = bcapclient.BCAPClient(HOST, PORT, TIMEOUT)
        print("[Robot] Open Connection")

        # start b_cap Service
        m_bcapclient.service_start("")
        print("[Robot] Send SERVICE_START packet")

        # Connect to RC8
        hCtrl = m_bcapclient.controller_connect("", PROVIDER, MACHINE, "")
        print("[Robot] Connect " + PROVIDER)
        
        # get Robot Object Handle
        HRobot = m_bcapclient.controller_getrobot(hCtrl, "Arm", "")
        print("[Robot] AddRobot")

        # TakeArm
        Command = "TakeArm"
        Param = [0, 0]
        m_bcapclient.robot_execute(HRobot, Command, Param)
        print("[Robot] TakeArm Done")

        # Motor On
        Command = "Motor"
        Param = [1, 0]
        m_bcapclient.robot_execute(HRobot, Command, Param)
        print("[Robot] Motor On Done")

        # ★★★ ここに実際のロボット動作（Moveなど）を書く ★★★
        # 例: 変数 P1 を動かす場合
        # Command = "Move"
        # Param = [1, "P1", "NEXT"]
        # m_bcapclient.robot_execute(HRobot, Command, Param)

                
        # # 4ｍｍ/secで現在位置(current_pos)からz軸方向に50mm移動する
        # vSp = m_bcapclient.robot_execute(HRobot, "MPS", [4])
        # Option = "SPEED=" + str(vSp) + ", ACCEL=100, DECEL=100, NEXT"
        # # 現在位置からz方向に移動
        # current_pos = m_bcapclient.robot_execute(HRobot, "CurPos")
        # relative_pos = m_bcapclient.robot_execute(HRobot, "DevH", [current_pos, "P(0, 0, 50, 0, 0, 0)" ]) #第一引数を基準にツール座標系の相対位置を計算
        # Pose = [relative_pos, "P", "@P"]
        # m_bcapclient.robot_move(HRobot,2,Pose,Option)
        base_pos = m_bcapclient.robot_execute(HRobot, "CurPos")
        vSp = m_bcapclient.robot_execute(HRobot, "MPS", [4])
        option_z = "SPEED=" + str(vSp) + ", ACCEL=100, DECEL=100, NEXT"
        option_y = "SPEED=10"

        for i in range(5):
            print(f"動作 {i+1} 回目")

            # Z +30
            relative_z_up = m_bcapclient.robot_execute(HRobot, "DevH", [base_pos, "P(0, 0, 40, 0, 0, 0)"])
            pose_z_up = [relative_z_up, "P", "@P"]
            m_bcapclient.robot_move(HRobot, 2, pose_z_up, option_z)

            # Z 戻る（base_posへ）
            pose_z_down = [base_pos, "P", "@P"]
            m_bcapclient.robot_move(HRobot, 2, pose_z_down, option_y)

            # Y +10
            base_pos = m_bcapclient.robot_execute(HRobot, "DevH", [base_pos, "P(0, 5, 0, 0, 0, 0)"])
            pose_y = [base_pos, "P", "@P"]
            m_bcapclient.robot_move(HRobot, 2, pose_y, option_y)

        # 動作確認のため、とりあえず5秒待機（この間もログは取れています）
        # print("[Robot] 5秒間待機します(ログ取得中)...")
        time.sleep(5)

        # Motor Off (終了時)
        Command = "Motor"
        Param = [0, 0]
        m_bcapclient.robot_execute(HRobot, Command, Param)
        print("[Robot] Motor Off")

        # Disconnect
        if hCtrl is not None:
            m_bcapclient.controller_disconnect(hCtrl)
        m_bcapclient.service_stop()
        print("[Robot] b-CAP Service Stop")

    except Exception as e:
        print(f"[Robot] Error: {e}")

    finally:
        # 3. 終了処理
        # -------------------------------------------------
        print("全ての処理が終了しました。ログ記録を停止します。")
        stop_event.set() # ログスレッドに停止を通知
        logger_thread.join() # スレッドが完全に終わるのを待つ

if __name__ == '__main__':
    main()