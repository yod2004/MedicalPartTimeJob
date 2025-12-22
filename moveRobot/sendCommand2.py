import bcapclient
import serial
import time
import csv
import datetime
import threading
import os
import sys
import numpy as np
import cv2
from ctypes import *

# ★★★ 追加部分：DLLのフォルダを登録する ★★★
# あなたのPCの「MvCameraControl.dll」があるフォルダパスを指定します
dll_dir = r"C:\Program Files\Common Files\MVS\Runtime\Win64_x64"
if os.path.exists(dll_dir):
    os.add_dll_directory(dll_dir)
    print(f"DLLディレクトリを追加しました: {dll_dir}")
else:
    print(f"警告: DLLディレクトリが見つかりません: {dll_dir}")

# --- Shodenshaカメラ用ライブラリ ---
try:
    from Shodensha.MvCameraControl_class import *
    from Shodensha.CameraParams_const import *
except ImportError:
    print("【警告】Shodenshaライブラリが見つかりません。")

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

# --- 設定: カメラ ---
CAMERA_FPS = 10
SAVE_DIR_BASE = "captured_images"

# 停止用フラグ
stop_event = threading.Event()

# ==========================================
#  タスク1: シリアル通信ログ (Arduino)
# ==========================================
def serial_logger_task():
    try:
        ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=1)
        print(f"[Serial] {COM_PORT} に接続しました。")
    except serial.serialutil.SerialException:
        print("[Serial] ポートが見つかりません。ログ記録をスキップします。")
        return

    time.sleep(2)

    with open(OUTPUT_FILE, 'a', newline='') as f:
        writer = csv.writer(f)
        headers = ['Time', 'Current', 'AcX', 'AcY', 'AcZ', 'GyX', 'GyY', 'GyZ', 'Freq']
        writer.writerow(headers)
        
        print(f"[Serial] 計測を開始します... 保存先: {OUTPUT_FILE}")
        ser.write(b's')

        try:
            while not stop_event.is_set():
                if ser.in_waiting > 0:
                    try:
                        line = ser.readline().decode('utf-8').strip()
                        if not line: continue
                        parts = line.split(',')
                        if len(parts) >= 8:
                            try:
                                float(parts[0])
                                now = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
                                writer.writerow([now] + parts)
                            except ValueError:
                                pass
                    except UnicodeDecodeError:
                        pass
        finally:
            print("[Serial] 停止コマンド送信...")
            ser.write(b'e')
            time.sleep(0.5)
            ser.close()

# ==========================================
#  タスク2: カメラ撮影 (初期化済みのcamを受け取る)
# ==========================================
def camera_logger_task(cam, buf, buf_size, frame_info, save_dir):
    print(f"[Camera] 撮影スレッド開始。保存先: {save_dir}")
    
    try:
        while not stop_event.is_set():
            start_time = time.time()

            # 1. ソフトウェアトリガー
            ret = cam.MV_CC_SetCommandValue("TriggerSoftware")
            
            # 2. 画像取得 (Timeout 1000ms)
            ret = cam.MV_CC_GetOneFrameTimeout(buf, buf_size, frame_info, 1000)
            
            if ret == 0:
                # 画像サイズ取得
                width = frame_info.nWidth
                height = frame_info.nHeight
                
                # NumPy配列に変換
                img_array = np.frombuffer(buf, dtype=np.uint8, count=frame_info.nFrameLen)
                
                # モノクロ(Mono8)としてリシェイプ
                if frame_info.enPixelType == 17301505: # PixelType_Gvsp_Mono8
                     img_array = img_array.reshape((height, width))
                
                # ファイル名作成 (タイムスタンプ)
                ts_str = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                filename = os.path.join(save_dir, f"img_{ts_str}.png")
                
                # 保存
                cv2.imwrite(filename, img_array)
            else:
                pass # タイムアウト等は無視して次へ

            # FPS制御
            elapsed = time.time() - start_time
            sleep_time = (1.0 / CAMERA_FPS) - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    except Exception as e:
        print(f"[Camera] エラー: {e}")

# ==========================================
#  メイン処理
# ==========================================
def main():
    # -------------------------------------------------
    # 1. カメラ初期化 (メインスレッドで実行)
    # -------------------------------------------------
    print("[Main] カメラを探しています...")
    cam = MvCamera()
    deviceList = MV_CC_DEVICE_INFO_LIST()
    ret = MvCamera.MV_CC_EnumDevices(MV_GIGE_DEVICE | MV_USB_DEVICE, deviceList)

    camera_ready = False
    buf = None
    buf_size = 0
    frame_info = None
    save_dir = ""

    if ret == 0 and deviceList.nDeviceNum > 0:
        print(f"[Camera] {deviceList.nDeviceNum} 台のカメラが見つかりました。接続します...")
        stDeviceInfo = cast(deviceList.pDeviceInfo[0], POINTER(MV_CC_DEVICE_INFO)).contents
        cam.MV_CC_CreateHandle(stDeviceInfo)
        ret = cam.MV_CC_OpenDevice(MV_ACCESS_Exclusive, 0)
        
        if ret == 0:
            # 設定
            cam.MV_CC_SetEnumValue("TriggerMode", MV_TRIGGER_MODE_ON)
            cam.MV_CC_SetEnumValue("TriggerSource", MV_TRIGGER_SOURCE_SOFTWARE)
            cam.MV_CC_StartGrabbing()
            
            # バッファ確保
            buf_size = 1920 * 1080 * 3
            buf = (c_ubyte * buf_size)()
            frame_info = MV_FRAME_OUT_INFO_EX()
            
            # 保存フォルダ作成
            current_time_str = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            save_dir = os.path.join(SAVE_DIR_BASE, current_time_str)
            os.makedirs(save_dir, exist_ok=True)
            
            camera_ready = True
            print("[Camera] 準備完了")
        else:
            print(f"[Camera] オープン失敗: {hex(ret)}")
    else:
        print("[Camera] カメラが見つかりません (MVSで認識されているか確認してください)")

    # -------------------------------------------------
    # 2. スレッド開始
    # -------------------------------------------------
    serial_thread = threading.Thread(target=serial_logger_task)
    serial_thread.start()

    if camera_ready:
        # 引数でcamインスタンスを渡す
        camera_thread = threading.Thread(target=camera_logger_task, args=(cam, buf, buf_size, frame_info, save_dir))
        camera_thread.start()
    
    time.sleep(3) # 安定待ち

    # -------------------------------------------------
    # 3. ロボット動作 (メインスレッド)
    # -------------------------------------------------
    hCtrl = None
    try:
        print("[Robot] Connecting to b-CAP...")
        m_bcapclient = bcapclient.BCAPClient(HOST, PORT, TIMEOUT)
        print("[Robot] Open Connection")
        m_bcapclient.service_start("")
        
        hCtrl = m_bcapclient.controller_connect("", PROVIDER, MACHINE, "")
        print("[Robot] Connected")
        HRobot = m_bcapclient.controller_getrobot(hCtrl, "Arm", "")

        # Motor On
        m_bcapclient.robot_execute(HRobot, "TakeArm", [0, 0])
        m_bcapclient.robot_execute(HRobot, "Motor", [1, 0])
        print("[Robot] Motor On")

        # --- 動作ループ ---
        base_pos = m_bcapclient.robot_execute(HRobot, "CurPos")
        vSp = m_bcapclient.robot_execute(HRobot, "MPS", [4])
        option_z = "SPEED=" + str(vSp) + ", ACCEL=100, DECEL=100, NEXT"
        option_y = "SPEED=10"

        for i in range(5):
            print(f"[Robot] 動作 {i+1}/5")
            
            # Z +40
            relative_z_up = m_bcapclient.robot_execute(HRobot, "DevH", [base_pos, "P(0, 0, 40, 0, 0, 0)"])
            m_bcapclient.robot_move(HRobot, 2, [relative_z_up, "P", "@P"], option_z)

            # Z Return
            m_bcapclient.robot_move(HRobot, 2, [base_pos, "P", "@P"], option_y)

            # Y +5
            base_pos = m_bcapclient.robot_execute(HRobot, "DevH", [base_pos, "P(0, 5, 0, 0, 0, 0)"])
            m_bcapclient.robot_move(HRobot, 2, [base_pos, "P", "@P"], option_y)

        print("[Robot] 動作完了。待機中...")
        time.sleep(5)

        # Motor Off
        m_bcapclient.robot_execute(HRobot, "Motor", [0, 0])
        
        if hCtrl is not None:
            m_bcapclient.controller_disconnect(hCtrl)
        m_bcapclient.service_stop()
        print("[Robot] Disconnected")

    except Exception as e:
        print(f"[Robot] Error: {e}")

    finally:
        print("終了処理中...")
        stop_event.set()
        serial_thread.join()
        if camera_ready:
            camera_thread.join()
            cam.MV_CC_StopGrabbing()
            cam.MV_CC_CloseDevice()
            cam.MV_CC_DestroyHandle()
        print("Done.")

if __name__ == '__main__':
    main()