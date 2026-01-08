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
import glob
import tkinter as tk
from tkinter import filedialog

# --- データ可視化用ライブラリ ---
try:
    import pandas as pd
    import matplotlib.pyplot as plt
    # CheckButtonsを追加
    from matplotlib.widgets import Slider, CheckButtons
except ImportError:
    print("【警告】pandas または matplotlib がありません。可視化機能はスキップされます。")

# ==============================================================================
# 【重要】DLLのパスを通す処理
# ==============================================================================
dll_paths = [
    r"C:\Program Files\Common Files\MVS\Runtime\Win64_x64",
    r"C:\Program Files (x86)\Common Files\MVS\Runtime\Win64_x64"
]
for path in dll_paths:
    if os.path.exists(path):
        try:
            os.add_dll_directory(path)
            break
        except Exception:
            pass

# --- Shodenshaカメラ用ライブラリ ---
HAS_CAMERA_LIB = False
try:
    from Shodensha.MvCameraControl_class import *
    from Shodensha.CameraParams_const import *
    HAS_CAMERA_LIB = True
except ImportError:
    print("【警告】Shodenshaカメラライブラリが見つかりません。カメラ機能は無効化されます。")

# --- bcapclient (ロボット用) ---
HAS_ROBOT_LIB = False
try:
    import bcapclient
    HAS_ROBOT_LIB = True
except ImportError:
    print("【警告】bcapclient が見つかりません。ロボット通信はスキップされます。")


# ==============================================================================
#  設定
# ==============================================================================
COM_PORT = 'COM18'
BAUD_RATE = 460800

# ロボット接続設定
HOST = "10.1.1.190"
PORT = 5007
TIMEOUT = 2000
PROVIDER = "CaoProv.DENSO.VRC9"
MACHINE = "localhost"

CAMERA_FPS = 10
SAVE_DIR_BASE = "captured_images"
LOG_DIR_BASE = "sensor_logs"

stop_event = threading.Event()

# ==========================================
#  タスク: シリアル通信
# ==========================================
def serial_logger_task(csv_filepath):
    try:
        ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=1)
        print(f"[Serial] {COM_PORT} に接続しました。")
    except serial.serialutil.SerialException:
        print("[Serial] ポートが見つかりません。ログ記録をスキップします。")
        return

    time.sleep(2)
    
    with open(csv_filepath, 'w', newline='') as f:
        writer = csv.writer(f)
        headers = [
            'Time', 
            'Current', 
            'AcX', 'AcY', 'AcZ', 
            'GyX', 'GyY', 'GyZ', 
            'Fx', 'Fy', 'Fz', 'Mx', 'My', 'Mz',
            'Freq'
        ]
        writer.writerow(headers)
        
        print(f"[Serial] 計測開始... 保存先: {csv_filepath}")
        ser.write(b's')

        try:
            while not stop_event.is_set():
                if ser.in_waiting > 0:
                    try:
                        line = ser.readline().decode('utf-8').strip()
                        if not line: continue
                        parts = line.split(',')
                        
                        # 既存8 + 新規6 = 14列以上あるか確認
                        if len(parts) >= 14:
                            try:
                                float(parts[0]) # 数値変換チェック
                                now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
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
#  タスク: カメラ撮影
# ==========================================
def camera_logger_task(cam, buf, buf_size, frame_info, save_dir):
    print(f"[Camera] 撮影スレッド開始。保存先: {save_dir}")
    try:
        while not stop_event.is_set():
            start_time = time.time()
            if cam:
                ret = cam.MV_CC_SetCommandValue("TriggerSoftware")
                ret = cam.MV_CC_GetOneFrameTimeout(buf, buf_size, frame_info, 1000)
                
                if ret == 0:
                    width = frame_info.nWidth
                    height = frame_info.nHeight
                    img_array = np.frombuffer(buf, dtype=np.uint8, count=frame_info.nFrameLen)
                    
                    if frame_info.enPixelType == 17301505: # Mono8
                        img_array = img_array.reshape((height, width))
                    
                    ts_str = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                    filename = os.path.join(save_dir, f"img_{ts_str}.png")
                    cv2.imwrite(filename, img_array)
            
            elapsed = time.time() - start_time
            sleep_time = (1.0 / CAMERA_FPS) - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
    except Exception as e:
        print(f"[Camera] エラー: {e}")

# ==========================================
#  可視化機能 (チェックボックス対応版)
# ==========================================
def visualize_results(csv_path, img_dir):
    print(f"\n[Visualizer] 起動中...\n CSV: {csv_path}\n IMG: {img_dir}")
    
    if not os.path.exists(csv_path):
        print("[Visualizer] CSVファイルが見つかりません。")
        return

    try:
        df = pd.read_csv(csv_path)
        df['dt'] = pd.to_datetime(df['Time'], format='%Y-%m-%d %H:%M:%S.%f', errors='coerce')
        df = df.dropna(subset=['dt'])
        
        if df.empty:
            print("[Visualizer] 有効なデータがありませんでした。")
            return

        start_time = df['dt'].iloc[0]
        df['Elapsed'] = (df['dt'] - start_time).dt.total_seconds()
        
        # 数値変換 (プロット可能な列を特定するため)
        numeric_cols = ['Current', 'AcX', 'AcY', 'AcZ', 'GyX', 'GyY', 'GyZ', 
                        'Freq', 'Fx', 'Fy', 'Fz', 'Mx', 'My', 'Mz']
        
        # 実際にCSVに存在する列のみを対象にする
        plot_targets = []
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                plot_targets.append(col)
        
        if not plot_targets:
            print("[Visualizer] プロット可能な数値データ列が見つかりません。")
            return

    except Exception as e:
        print(f"[Visualizer] CSV読み込みエラー: {e}")
        return

    # 画像リスト作成
    img_files = sorted(glob.glob(os.path.join(img_dir, "*.png")))
    img_data = []
    for f in img_files:
        basename = os.path.basename(f)
        try:
            ts_part = basename.replace("img_", "").replace(".png", "")
            dt = datetime.datetime.strptime(ts_part, '%Y%m%d_%H%M%S_%f')
            img_data.append({'path': f, 'dt': dt})
        except ValueError:
            continue
    
    if img_data:
        df_img = pd.DataFrame(img_data)
    else:
        print("[Visualizer] 画像が見つかりませんが、グラフのみ表示します。")
        df_img = pd.DataFrame(columns=['path', 'dt'])

    # --- 描画セットアップ ---
    # 右側にチェックボックス用のスペースを空けるため、figsizeを広げ、adjustを行う
    fig, (ax_graph, ax_img) = plt.subplots(1, 2, figsize=(16, 7))
    plt.subplots_adjust(left=0.05, bottom=0.25, right=0.8, top=0.9) # right=0.8で右側20%を空ける

    # グラフ描画（全データを一度プロットし、オブジェクトを保存しておく）
    lines = []
    lines_map = {} # 名前とLineオブジェクトの対応辞書

    # カラーマップを使用（項目が多いので色が重ならないように）
    colors = plt.cm.tab20(np.linspace(0, 1, len(plot_targets)))

    for i, col in enumerate(plot_targets):
        ln, = ax_graph.plot(df['Elapsed'], df[col], label=col, color=colors[i], lw=1.5)
        lines.append(ln)
        lines_map[col] = ln
    
    ax_graph.set_title("Sensor Data Log")
    ax_graph.set_xlabel("Time (sec)")
    ax_graph.set_ylabel("Value")
    ax_graph.grid(True)
    
    # 凡例はチェックボックスがあるので非表示にするか、邪魔にならない位置に
    # ax_graph.legend(loc='upper left', fontsize='small') 
    
    vline = ax_graph.axvline(x=0, color='red', linestyle='--', lw=1)

    # --- チェックボックスの作成 ---
    # 右側の空きスペースに配置 [left, bottom, width, height]
    ax_check = plt.axes([0.82, 0.25, 0.15, 0.65])
    ax_check.set_title("Data Select", fontsize=10)
    
    # 全てTrue(チェック済み)で初期化
    visibility = [True] * len(plot_targets)
    check = CheckButtons(ax_check, plot_targets, visibility)

    # チェックボックスの文字色を線の色と合わせる（視認性向上）
    for r, col_name in enumerate(plot_targets):
        check.labels[r].set_color(lines_map[col_name].get_color())
        # check.rectangles[r].set_facecolor(...) # チェックボックス自体の色を変えたい場合

    # --- コールバック関数: 表示切替とY軸オートスケール ---
    def on_check_click(label):
        ln = lines_map[label]
        ln.set_visible(not ln.get_visible())
        
        # 表示されているラインのデータに基づいてY軸を再スケーリング
        visible_lines = [l for l in lines if l.get_visible()]
        if visible_lines:
            min_y = float('inf')
            max_y = float('-inf')
            
            # 現在表示中のグラフデータの最小・最大を探す
            for l in visible_lines:
                y_data = l.get_ydata()
                if len(y_data) > 0:
                    min_y = min(min_y, np.min(y_data))
                    max_y = max(max_y, np.max(y_data))
            
            # マージンを少し持たせる
            if min_y != float('inf') and max_y != float('-inf'):
                margin = (max_y - min_y) * 0.05
                if margin == 0: margin = 1.0
                ax_graph.set_ylim(min_y - margin, max_y + margin)
        
        plt.draw()

    check.on_clicked(on_check_click)

    # --- 画像表示 ---
    img_obj = None
    if not df_img.empty:
        init_img = cv2.imread(df_img.iloc[0]['path'], cv2.IMREAD_GRAYSCALE)
        if init_img is not None:
            img_obj = ax_img.imshow(init_img, cmap='gray', vmin=0, vmax=255)
            ax_img.set_title("Camera View")
            ax_img.axis('off')
    else:
        ax_img.text(0.5, 0.5, "No Image", ha='center')
        ax_img.axis('off')

    # --- スライダー ---
    ax_slider = plt.axes([0.2, 0.1, 0.4, 0.03])
    slider = Slider(ax_slider, 'Time', 0, df['Elapsed'].max(), valinit=0)

    def update(val):
        current_time_sec = slider.val
        vline.set_xdata([current_time_sec, current_time_sec])
        
        if not df_img.empty:
            target_dt = start_time + datetime.timedelta(seconds=current_time_sec)
            nearest_idx = (df_img['dt'] - target_dt).abs().idxmin()
            img_path = df_img.iloc[nearest_idx]['path']
            
            new_img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
            if new_img is not None and img_obj is not None:
                img_obj.set_data(new_img)
                ax_img.set_title(f"Camera View\n{os.path.basename(img_path)}")
        fig.canvas.draw_idle()

    slider.on_changed(update)
    print("[Visualizer] ウィンドウを表示します。右側のボックスで表示データを選択できます。")
    plt.show()

# ==========================================
#  モード A: 計測を実行する
# ==========================================
def run_measurement_mode():
    now_str = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    
    os.makedirs(LOG_DIR_BASE, exist_ok=True)
    save_dir_img = os.path.join(SAVE_DIR_BASE, now_str)
    os.makedirs(save_dir_img, exist_ok=True)
    
    csv_filepath = os.path.join(LOG_DIR_BASE, f"log_{now_str}.csv")

    # --- カメラ準備 ---
    print("[Main] カメラを探しています...")
    cam = None
    camera_ready = False
    buf = None
    buf_size = 0
    frame_info = None

    if HAS_CAMERA_LIB:
        try:
            cam = MvCamera()
            deviceList = MV_CC_DEVICE_INFO_LIST()
            ret = MvCamera.MV_CC_EnumDevices(MV_GIGE_DEVICE | MV_USB_DEVICE, deviceList)

            if ret == 0 and deviceList.nDeviceNum > 0:
                stDeviceInfo = cast(deviceList.pDeviceInfo[0], POINTER(MV_CC_DEVICE_INFO)).contents
                cam.MV_CC_CreateHandle(stDeviceInfo)
                ret = cam.MV_CC_OpenDevice(MV_ACCESS_Exclusive, 0)
                if ret == 0:
                    cam.MV_CC_SetEnumValue("TriggerMode", MV_TRIGGER_MODE_ON)
                    cam.MV_CC_SetEnumValue("TriggerSource", MV_TRIGGER_SOURCE_SOFTWARE)
                    cam.MV_CC_StartGrabbing()
                    buf_size = 1920 * 1080 * 3
                    buf = (c_ubyte * buf_size)()
                    frame_info = MV_FRAME_OUT_INFO_EX()
                    camera_ready = True
                    print("[Camera] 準備完了")
                else:
                    print(f"[Camera] オープン失敗: {hex(ret)}")
            else:
                print("[Camera] 未検出 (スキップします)")
        except Exception as e:
            print(f"[Camera] 初期化中に例外発生: {e}")
    else:
        print("[Camera] ライブラリなしのためスキップ")

    # --- スレッド開始 ---
    stop_event.clear()
    
    serial_thread = threading.Thread(target=serial_logger_task, args=(csv_filepath,))
    serial_thread.start()

    camera_thread = None
    if camera_ready and cam is not None:
        camera_thread = threading.Thread(target=camera_logger_task, args=(cam, buf, buf_size, frame_info, save_dir_img))
        camera_thread.start()
    
    time.sleep(3)

    # --- ロボット動作 ---
    if HAS_ROBOT_LIB:
        hCtrl = None
        try:
            print("[Robot] Connecting...")
            m_bcapclient = bcapclient.BCAPClient(HOST, PORT, TIMEOUT)
            m_bcapclient.service_start("")
            hCtrl = m_bcapclient.controller_connect("", PROVIDER, MACHINE, "")
            HRobot = m_bcapclient.controller_getrobot(hCtrl, "Arm", "")

            m_bcapclient.robot_execute(HRobot, "TakeArm", [0, 0])
            m_bcapclient.robot_execute(HRobot, "Motor", [1, 0])
            
            base_pos = m_bcapclient.robot_execute(HRobot, "CurPos")
            vSp = m_bcapclient.robot_execute(HRobot, "MPS", [4])
            option_z = "SPEED=" + str(vSp) + ", ACCEL=100, DECEL=100, NEXT"
            option_y = "SPEED=10"

            for i in range(5):
                print(f"[Robot] 動作 {i+1}/5")
                relative_z_up = m_bcapclient.robot_execute(HRobot, "DevH", [base_pos, "P(0, 0, 40, 0, 0, 0)"])
                m_bcapclient.robot_move(HRobot, 2, [relative_z_up, "P", "@P"], option_z)
                m_bcapclient.robot_move(HRobot, 2, [base_pos, "P", "@P"], option_y)
                
                base_pos = m_bcapclient.robot_execute(HRobot, "DevH", [base_pos, "P(0, 5, 0, 0, 0, 0)"])
                m_bcapclient.robot_move(HRobot, 2, [base_pos, "P", "@P"], option_y)

            print("[Robot] 動作完了。5秒待機...")
            time.sleep(5)

            m_bcapclient.robot_execute(HRobot, "Motor", [0, 0])
            if hCtrl is not None:
                m_bcapclient.controller_disconnect(hCtrl)
            m_bcapclient.service_stop()

        except Exception as e:
            print(f"[Robot] Error: {e}")
    else:
        print("[Robot] ライブラリがないため動作シミュレーション (Wait 10s)")
        time.sleep(10)

    # --- 終了処理 ---
    print("終了処理中...")
    stop_event.set()
    serial_thread.join()
    
    if camera_ready and camera_thread is not None:
        camera_thread.join()
        try:
            cam.MV_CC_StopGrabbing()
            cam.MV_CC_CloseDevice()
            cam.MV_CC_DestroyHandle()
        except Exception:
            pass
    
    print("計測終了。ビューワーを起動します。")
    if camera_ready or os.path.exists(csv_filepath):
        visualize_results(csv_filepath, save_dir_img)

# ==========================================
#  モード B: 過去データを表示する
# ==========================================
def run_viewer_mode():
    root = tk.Tk()
    root.withdraw() 

    csv_path = filedialog.askopenfilename(
        title="1. ログファイル(csv) を選択",
        filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        initialdir=os.getcwd()
    )
    if not csv_path: return

    img_dir = filedialog.askdirectory(
        title="2. 画像フォルダを選択",
        initialdir=os.path.join(os.getcwd(), SAVE_DIR_BASE)
    )
    if not img_dir: return

    visualize_results(csv_path, img_dir)

# ==========================================
#  メインメニュー
# ==========================================
def main():
    while True:
        print("\n=== モード選択 ===")
        print("1: 計測を開始する")
        print("2: 過去のデータを表示する")
        print("q: 終了")
        
        choice = input(">> ").strip()

        if choice == '1':
            run_measurement_mode()
            break
        elif choice == '2':
            run_viewer_mode()
            break
        elif choice == 'q':
            break

if __name__ == '__main__':
    main()