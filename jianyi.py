import sys
import vlc
from PyQt5.QtWidgets import (QApplication, QWidget, QPushButton, QVBoxLayout,
                             QHBoxLayout, QSlider, QLabel, QFileDialog, QFrame,
                             QMessageBox)
from PyQt5.QtCore import Qt, QTimer, QDir, pyqtSlot
from PyQt5.QtGui import QIcon, QPalette, QColor
import os

class MediaPlayer(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("简易媒体播放器")
        self.setGeometry(100, 100, 800, 600)
        self.setMinimumSize(640, 480)

        icon_path = os.path.join(os.getcwd(), "icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.instance = vlc.Instance()
        self.media = None
        self.mediaplayer = self.instance.media_player_new()

        self.is_playing = False
        self.init_ui()
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.update_ui)

    def init_ui(self):
        # 视频显示区域
        self.video_frame = QFrame()
        self.video_frame.setStyleSheet("background-color: black;")
        self.palette = self.video_frame.palette()
        self.palette.setColor(QPalette.Window, QColor(0, 0, 0))
        self.video_frame.setPalette(self.palette)
        self.video_frame.setAutoFillBackground(True)

        # 按钮
        self.open_button = QPushButton("打开文件")
        self.play_button = QPushButton("播放")
        self.pause_button = QPushButton("暂停")
        self.stop_button = QPushButton("停止")

        # UI颜色设置
        button_style = "QPushButton { background-color: #FFB6C1; }"  # 粉色
        self.open_button.setStyleSheet(button_style)
        self.play_button.setStyleSheet(button_style)
        self.pause_button.setStyleSheet(button_style)
        self.stop_button.setStyleSheet(button_style)

        # 进度条
        self.time_slider = QSlider(Qt.Horizontal)
        self.time_slider.setRange(0, 0)
        self.time_slider.sliderReleased.connect(self.preview_play)  # 松开滑块时触发

        # 标签
        self.time_label = QLabel("00:00 / 00:00")

        # 布局
        control_layout = QHBoxLayout()
        control_layout.addWidget(self.open_button)
        control_layout.addWidget(self.play_button)
        control_layout.addWidget(self.pause_button)
        control_layout.addWidget(self.stop_button)

        slider_layout = QHBoxLayout()
        slider_layout.addWidget(self.time_slider)
        slider_layout.addWidget(self.time_label)

        # 顶部横条浅蓝色
        main_layout = QVBoxLayout()
        main_layout.addWidget(self.video_frame, 4)

        # 创建一个QWidget作为横条的背景
        toolbar_widget = QWidget()
        toolbar_widget.setStyleSheet("background-color: #ADD8E6;")  # 浅蓝色
        toolbar_layout = QVBoxLayout()
        toolbar_layout.setContentsMargins(0, 0, 0, 0)  # 移除边距
        toolbar_widget.setLayout(toolbar_layout)
        toolbar_layout.addLayout(control_layout)

        main_layout.addWidget(toolbar_widget)
        main_layout.addLayout(slider_layout)

        self.setLayout(main_layout)

        # 信号
        self.open_button.clicked.connect(self.open_file)
        self.play_button.clicked.connect(self.play)
        self.pause_button.clicked.connect(self.pause)
        self.stop_button.clicked.connect(self.stop)

    def closeEvent(self, event):
        if self.is_playing:
            QMessageBox.warning(self, "警告", "播放中途不能关闭窗口！")
            event.ignore()
        else:
            self.stop()
            event.accept()

    def open_file(self):
        filename, _ = QFileDialog.getOpenFileName(self, "选择媒体文件", "",
                                                  "媒体文件 (*.mp4 *.avi *.mp3 *.wav *.ogg)")
        if filename != "":
            try:
                self.media = self.instance.media_new(filename)
                self.mediaplayer.set_media(self.media)

                # 设置视频输出窗口
                if sys.platform.startswith('linux'):
                    self.mediaplayer.set_xwindow(self.video_frame.winId())
                elif sys.platform == "win32":
                    self.mediaplayer.set_hwnd(self.video_frame.winId())
                elif sys.platform == "darwin":
                    self.mediaplayer.set_nsobject(int(self.video_frame.winId()))

                self.play()
            except Exception as e:
                QMessageBox.critical(self, "错误", f"无法打开文件: {e}")

    def play(self):
        if self.media:
            if not self.is_playing:
                self.mediaplayer.play()
                self.is_playing = True
                self.play_button.setText("暂停")
                self.timer.start()
            else:
                self.mediaplayer.pause()
                self.is_playing = False
                self.play_button.setText("播放")
                self.timer.stop()

    def pause(self):
        if self.media and self.is_playing:
            self.mediaplayer.pause()
            self.is_playing = False
            self.play_button.setText("播放")
            self.timer.stop()

    def stop(self):
        if self.media:
            self.mediaplayer.stop()
            self.is_playing = False
            self.play_button.setText("播放")
            self.timer.stop()
            self.time_slider.setValue(0)
            self.time_label.setText("00:00 / 00:00")

    def update_ui(self):
        if self.mediaplayer.is_playing():
            length = self.mediaplayer.get_length()
            time = self.mediaplayer.get_time()
            self.time_slider.setRange(0, length)
            self.time_slider.setValue(time)
            self.time_label.setText(self.format_time(time) + " / " + self.format_time(length))

    def format_time(self, milliseconds):
        seconds = (milliseconds // 1000) % 60
        minutes = (milliseconds // (1000 * 60)) % 60
        return "{:02d}:{:02d}".format(minutes, seconds)

    def preview_play(self):
        if self.media:
            length = self.mediaplayer.get_length()
            position = self.time_slider.value()
            if length > 0:
                self.mediaplayer.set_time(int(position))
            self.mediaplayer.play()  # 从新的位置播放
            self.is_playing = True
            self.play_button.setText("暂停")
            self.timer.start()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    player = MediaPlayer()
    player.show()
    sys.exit(app.exec_())
