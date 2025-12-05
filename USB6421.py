import tkinter as tk
from tkinter import ttk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import nidaqmx
from nidaqmx.constants import AcquisitionType
from collections import deque

class RealTimeScopeApp:
    def __init__(self, root):
        self.root = root
        self.root.title("NI-DAQmx Simple Scope")

        # --- 設定 ---
        self.device_name = "Dev1"
        self.sampling_rate = 1000
        self.display_samples = 1000
        self.read_chunk = 50  # 一度に読み取るデータ数
        
        # 状態管理
        self.channels = ["ai0"] # 初期チャンネル
        self.lines = []
        self.data_queues = [deque([0]*self.display_samples, maxlen=self.display_samples)]
        self.task = None
        self.is_running = False

        # --- GUIの作成 ---
        # 1. 上部コントロールパネル
        control_frame = ttk.Frame(root)
        control_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)

        # チャンネル追加エリア
        ttk.Label(control_frame, text="CH追加 (例: ai1):").pack(side=tk.LEFT)
        self.entry_ch = ttk.Entry(control_frame, width=5)
        self.entry_ch.pack(side=tk.LEFT, padx=2)
        
        btn_add = ttk.Button(control_frame, text="追加", command=self.add_channel)
        btn_add.pack(side=tk.LEFT, padx=2)
        
        btn_reset = ttk.Button(control_frame, text="全クリア", command=self.clear_channels)
        btn_reset.pack(side=tk.LEFT, padx=5)

        # レンジ設定エリア
        ttk.Label(control_frame, text=" | Min(V):").pack(side=tk.LEFT)
        self.entry_min = ttk.Entry(control_frame, width=5)
        self.entry_min.insert(0, "-10")
        self.entry_min.pack(side=tk.LEFT, padx=2)

        ttk.Label(control_frame, text="Max(V):").pack(side=tk.LEFT)
        self.entry_max = ttk.Entry(control_frame, width=5)
        self.entry_max.insert(0, "10")
        self.entry_max.pack(side=tk.LEFT, padx=2)

        btn_range = ttk.Button(control_frame, text="レンジ更新", command=self.update_range)
        btn_range.pack(side=tk.LEFT, padx=5)

        # 現在のチャンネル表示ラベル
        self.lbl_status = ttk.Label(root, text=f"Active Channels: {self.channels}")
        self.lbl_status.pack(side=tk.TOP, fill=tk.X, padx=5)

        # 2. グラフエリア
        self.fig, self.ax = plt.subplots(figsize=(8, 5))
        self.ax.set_title("Real-time Monitor")
        self.ax.grid(True)
        self.ax.set_ylim(-10, 10)
        
        # 描画キャンバスをTkinterに埋め込む
        self.canvas = FigureCanvasTkAgg(self.fig, master=root)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # 初期描画の線をセットアップ
        self.setup_lines()

        # タスク開始
        self.start_task()

        # アニメーション設定
        self.ani = animation.FuncAnimation(
            self.fig, self.update_plot, interval=50, blit=True, cache_frame_data=False
        )

    def setup_lines(self):
        """グラフの線を初期化・再設定する"""
        self.ax.clear()
        self.ax.grid(True)
        self.ax.set_xlim(0, self.display_samples)
        self.update_range() # 現在の入力値でレンジ設定
        
        self.lines = []
        # 色のリスト（必要なら増やしてください）
        colors = ['b', 'g', 'r', 'c', 'm', 'y', 'k']
        
        for i, ch in enumerate(self.channels):
            col = colors[i % len(colors)]
            line, = self.ax.plot([], [], label=f"{ch}", color=col)
            self.lines.append(line)
        
        self.ax.legend(loc='upper right')

    def start_task(self):
        """NI-DAQmxタスクを開始する"""
        if not self.channels:
            return

        try:
            if self.task:
                self.task.close()
            
            self.task = nidaqmx.Task()
            for ch in self.channels:
                self.task.ai_channels.add_ai_voltage_chan(f"{self.device_name}/{ch}")
            
            self.task.timing.cfg_samp_clk_timing(
                rate=self.sampling_rate,
                sample_mode=AcquisitionType.CONTINUOUS
            )
            self.task.start()
            self.is_running = True
            print(f"Task started for: {self.channels}")
            
        except Exception as e:
            print(f"Error starting task: {e}")
            self.is_running = False

    def add_channel(self):
        """チャンネルを追加してタスクを再起動"""
        new_ch = self.entry_ch.get()
        if new_ch and new_ch not in self.channels:
            self.channels.append(new_ch)
            # 新しいチャンネル用のデータキューを作成
            self.data_queues.append(deque([0]*self.display_samples, maxlen=self.display_samples))
            
            self.lbl_status.config(text=f"Active Channels: {self.channels}")
            self.setup_lines() # グラフの線を再構築
            self.start_task()  # タスクを再構築して再開

    def clear_channels(self):
        """全チャンネルクリア"""
        self.channels = []
        self.data_queues = []
        self.lbl_status.config(text="Active Channels: []")
        if self.task:
            self.task.close()
            self.task = None
        self.ax.clear()
        self.canvas.draw()

    def update_range(self):
        """Y軸のレンジを更新"""
        try:
            ymin = float(self.entry_min.get())
            ymax = float(self.entry_max.get())
            self.ax.set_ylim(ymin, ymax)
            self.canvas.draw()
        except ValueError:
            pass

    def update_plot(self, frame):
        """アニメーション更新用コールバック"""
        if not self.is_running or not self.task:
            return self.lines

        try:
            # データ読み取り
            # チャンネルが1つの時は1次元リスト、複数の時は2次元リストが返るため統一する
            raw_data = self.task.read(number_of_samples_per_channel=self.read_chunk)
            
            if len(self.channels) == 1:
                input_data = [raw_data] # 2次元リスト形式に統一
            else:
                input_data = raw_data

            # データ更新
            for i, data_points in enumerate(input_data):
                self.data_queues[i].extend(data_points)
                self.lines[i].set_data(range(self.display_samples), self.data_queues[i])

            return self.lines

        except Exception as e:
            # エラーが出たら停止する（無限ループエラー防止）
            print(f"Read Error: {e}")
            self.is_running = False
            return self.lines

    def on_closing(self):
        """アプリ終了時の処理"""
        if self.task:
            self.task.close()
        self.root.destroy()

# --- メイン処理 ---
if __name__ == "__main__":
    root = tk.Tk()
    app = RealTimeScopeApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()