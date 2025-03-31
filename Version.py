import sys
import os
import re
import platform
import requests
import vlc
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QListWidgetItem, QPushButton, QLabel, QFrame,
    QFileDialog, QLineEdit, QMessageBox, QSlider, QStatusBar, QStyle
)
from PyQt5.QtCore import Qt, QUrl, QTimer
from PyQt5.QtGui import QIcon

# --- M3U 解析函数 (保持不变) ---
def parse_m3u(content):
    channels = []
    lines = content.splitlines()
    current_channel_info = {}
    extinf_pattern = re.compile(r'#EXTINF:(?P<duration>-?\d+)(?P<attributes>.*),\s*(?P<name>.*)')
    attribute_pattern = re.compile(r'([a-zA-Z0-9_-]+)=("[^"]*"|\S+)')
    for i, line in enumerate(lines):
        line = line.strip()
        if line.startswith('#EXTINF:'):
            current_channel_info = {'name': 'Unknown', 'url': None, 'group': 'Default', 'logo': None}
            match = extinf_pattern.match(line)
            if match:
                info = match.groupdict()
                base_name = info.get('name', 'Unknown').strip()
                current_channel_info['name'] = base_name
                attributes_str = info.get('attributes', '').strip()
                if attributes_str:
                    attributes = {}
                    for key, value in attribute_pattern.findall(attributes_str):
                        attributes[key.lower()] = value.strip('"')
                    current_channel_info['name'] = attributes.get('tvg-name', base_name)
                    current_channel_info['group'] = attributes.get('group-title', 'Default')
                    current_channel_info['logo'] = attributes.get('tvg-logo')
            if i + 1 < len(lines):
                 next_line = lines[i+1].strip()
                 if next_line and not next_line.startswith('#'):
                      current_channel_info['url'] = next_line
                      if current_channel_info['url']:
                          channels.append(current_channel_info.copy())
                          current_channel_info = {}
    print(f"解析到 {len(channels)} 个频道。")
    return channels

# --- 主播放器窗口 ---
class M3UPlayerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("M3U 直播播放器 (列表在右)") # 改下标题提示布局
        self.setGeometry(100, 100, 1000, 700)
        self.channels = []
        self.current_playing_item = None
        self.vlc_instance = None
        self.media_player = None
        self.event_manager = None
        self._initialize_vlc()
        self._setup_ui() # 使用修改后的 _setup_ui
        self._connect_signals()
        self._embed_vlc()

    def _initialize_vlc(self):
        vlc_options = ["--no-video-title-show", "--network-caching=1500"]
        try:
            self.vlc_instance = vlc.Instance(vlc_options)
            self.media_player = self.vlc_instance.media_player_new()
            if self.media_player:
                 self.event_manager = self.media_player.event_manager()
            else:
                 raise vlc.VLCException("无法创建 VLC Media Player 对象")
        except Exception as e:
            QMessageBox.critical(self, "VLC 初始化错误", f"无法初始化 VLC。\n错误: {e}")
            sys.exit(1)

    def _setup_ui(self): # <--- 修改后的方法
        """创建和布局 UI 元素 (列表在右侧)"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # --- 左侧面板 (现在是视频和控制) ---
        video_panel_widget = QWidget()
        video_panel_layout = QVBoxLayout(video_panel_widget)
        self.video_frame = QFrame()
        self.video_frame.setStyleSheet("background-color: black;")
        video_panel_layout.addWidget(self.video_frame, 1) # 视频区域占满
        control_layout = QHBoxLayout()
        style = self.style()
        self.play_pause_button = QPushButton()
        self.play_pause_button.setIcon(style.standardIcon(QStyle.SP_MediaPlay))
        self.play_pause_button.setEnabled(False)
        self.play_pause_button.setToolTip("播放")
        self.stop_button = QPushButton()
        self.stop_button.setIcon(style.standardIcon(QStyle.SP_MediaStop))
        self.stop_button.setEnabled(False)
        self.stop_button.setToolTip("停止")
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setMaximum(100)
        try:
            initial_volume = self.media_player.audio_get_volume()
            self.volume_slider.setValue(initial_volume if 0 <= initial_volume <= 100 else 70)
        except Exception:
            self.volume_slider.setValue(70)
        self.volume_slider.setToolTip("音量")
        control_layout.addWidget(self.play_pause_button)
        control_layout.addWidget(self.stop_button)
        control_layout.addStretch(1)
        control_layout.addWidget(QLabel("音量:"))
        control_layout.addWidget(self.volume_slider)
        video_panel_layout.addLayout(control_layout)

        # --- 右侧面板 (现在是加载和列表) ---
        list_panel_widget = QWidget()
        list_panel_layout = QVBoxLayout(list_panel_widget)
        list_panel_widget.setFixedWidth(300) # 固定宽度
        load_layout = QHBoxLayout()
        self.m3u_path_input = QLineEdit()
        self.m3u_path_input.setPlaceholderText("输入 M3U URL 或点击浏览")
        self.browse_button = QPushButton("浏览")
        self.load_url_button = QPushButton("加载URL")
        load_layout.addWidget(self.m3u_path_input)
        load_layout.addWidget(self.browse_button)
        load_layout.addWidget(self.load_url_button)
        list_panel_layout.addLayout(load_layout)
        self.channel_list_widget = QListWidget()
        list_panel_layout.addWidget(self.channel_list_widget)

        # --- 组合主布局 (关键改动！) ---
        main_layout.addWidget(video_panel_widget, 1) # 视频面板在左，占主要空间
        main_layout.addWidget(list_panel_widget)    # 列表面板在右，固定宽度

        # --- 状态栏 ---
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪")

    def _connect_signals(self):
        self.browse_button.clicked.connect(self._browse_m3u_file)
        self.load_url_button.clicked.connect(self._load_m3u_from_url)
        self.channel_list_widget.itemDoubleClicked.connect(self._play_selected_channel)
        self.play_pause_button.clicked.connect(self._toggle_play_pause)
        self.stop_button.clicked.connect(self._stop_playback)
        self.volume_slider.valueChanged.connect(self._set_volume)
        if self.event_manager:
            events_to_handle = [
                vlc.EventType.MediaPlayerOpening, vlc.EventType.MediaPlayerBuffering,
                vlc.EventType.MediaPlayerPlaying, vlc.EventType.MediaPlayerPaused,
                vlc.EventType.MediaPlayerStopped, vlc.EventType.MediaPlayerEncounteredError
            ]
            for event_type in events_to_handle:
                try:
                    self.event_manager.event_attach(event_type, self._handle_player_state_change)
                    print(f"成功绑定 VLC 事件: {event_type}")
                except Exception as e:
                    print(f"警告: 无法绑定 VLC 事件 {event_type}. 错误: {e}")
        else:
            QMessageBox.critical(self, "严重错误", "VLC 事件管理器未初始化！")
            sys.exit(1)

    def _embed_vlc(self):
        if not self.media_player: return
        try:
            system = platform.system()
            win_id = int(self.video_frame.winId())
            if system == "Linux": self.media_player.set_xwindow(win_id)
            elif system == "Windows": self.media_player.set_hwnd(win_id)
            elif system == "Darwin": self.media_player.set_nsobject(win_id)
            else: print(f"警告：不支持的平台 '{system}' 用于 VLC 嵌入。")
        except Exception as e: print(f"嵌入 VLC 到窗口时出错: {e}")

    def _browse_m3u_file(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "选择 M3U 文件", "", "M3U Playlist (*.m3u *.m3u8);;All Files (*)")
        if filepath:
            self.m3u_path_input.setText(filepath)
            self.status_bar.showMessage(f"加载中: {os.path.basename(filepath)}...")
            QApplication.processEvents()
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f: content = f.read()
                self.channels = parse_m3u(content)
                self._populate_channel_list()
                self.status_bar.showMessage(f"加载完成: {len(self.channels)} 频道")
            except Exception as e:
                QMessageBox.warning(self, "文件错误", f"无法加载或解析文件: {filepath}\n错误: {e}")
                self.status_bar.showMessage("加载失败")

    def _load_m3u_from_url(self):
        url = self.m3u_path_input.text().strip()
        if not url.startswith(('http://', 'https://')):
            QMessageBox.warning(self, "无效 URL", "请输入有效的 HTTP 或 HTTPS URL。")
            return
        self.status_bar.showMessage(f"加载中: {url}...")
        QApplication.processEvents()
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36'}
            response = requests.get(url, timeout=15, headers=headers, stream=True)
            response.raise_for_status()
            content = ""
            try: content = response.content.decode(response.encoding or 'utf-8', errors='ignore')
            except Exception as decode_error:
                 print(f"解码警告: {decode_error}. 尝试备用编码...")
                 try: content = response.content.decode('iso-8859-1', errors='ignore')
                 except Exception as final_decode_error: raise ValueError("无法解码服务器响应内容") from final_decode_error
            self.channels = parse_m3u(content)
            self._populate_channel_list()
            self.status_bar.showMessage(f"加载完成: {len(self.channels)} 频道")
        except requests.exceptions.Timeout:
             QMessageBox.warning(self, "网络错误", f"加载 URL 超时: {url}")
             self.status_bar.showMessage("加载超时")
        except requests.exceptions.RequestException as e:
            QMessageBox.warning(self, "网络错误", f"无法加载 URL: {url}\n错误: {e}")
            self.status_bar.showMessage(f"加载失败: 网络错误")
        except ValueError as e:
             QMessageBox.warning(self, "内容错误", f"{e}")
             self.status_bar.showMessage("加载失败：内容解码错误")
        except Exception as e:
            QMessageBox.warning(self, "未知错误", f"加载或处理 URL 时发生错误: {e}")
            self.status_bar.showMessage(f"加载失败：未知错误")

    def _populate_channel_list(self):
        self._stop_playback()
        self.channel_list_widget.clear()
        if not self.channels:
             self.channel_list_widget.addItem("列表为空或加载失败")
             return
        default_bg_color = self.channel_list_widget.palette().base()
        for channel in self.channels:
            item_text = channel.get('name', '未知频道')
            group = channel.get('group', 'Default')
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, channel)
            item.setToolTip(f"分组: {group}\nURL: {channel.get('url', 'N/A')}")
            item.setBackground(default_bg_color)
            self.channel_list_widget.addItem(item)

    def _play_selected_channel(self, item=None):
        if item is None: item = self.channel_list_widget.currentItem()
        if not item: return
        channel_data = item.data(Qt.UserRole)
        if channel_data and channel_data.get('url'):
            url = channel_data['url']
            name = channel_data.get('name', '未知频道')
            print(f"请求播放: {name} - {url}")
            self.status_bar.showMessage(f"准备加载: {name}...")
            try:
                if self.media_player.get_state() != vlc.State.Stopped: self.media_player.stop()
                media = self.vlc_instance.media_new(url)
                ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36"
                media.add_option(f'http-user-agent={ua}')
                self.media_player.set_media(media)
                media.release()
                play_result = self.media_player.play()
                if play_result == -1: raise RuntimeError("VLC media_player.play() 返回 -1")
                self.setWindowTitle(f"加载中: {name} - M3U 直播播放器")
                if self.current_playing_item and self.current_playing_item != item:
                     self.current_playing_item.setBackground(self.channel_list_widget.palette().base())
                item.setBackground(Qt.lightGray)
                self.current_playing_item = item
            except Exception as e:
                QMessageBox.warning(self, "播放启动错误", f"无法开始播放流: {name}\nURL: {url}\n错误: {e}")
                self.status_bar.showMessage(f"播放失败: {name}")
                self._stop_playback()
        else: QMessageBox.information(self, "信息", "选中的频道没有有效的播放地址。")

    def _toggle_play_pause(self):
        if not self.media_player: return
        if self.media_player.is_playing(): self.media_player.pause()
        elif self.media_player.can_pause(): self.media_player.play()

    def _stop_playback(self):
        print("请求停止播放...")
        if self.media_player and self.media_player.get_state() != vlc.State.Stopped: self.media_player.stop()
        self.play_pause_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self._update_play_pause_icon()
        self.status_bar.showMessage("已停止")
        self.setWindowTitle("M3U 直播播放器 (列表在右)")
        if self.current_playing_item:
            self.current_playing_item.setBackground(self.channel_list_widget.palette().base())
            self.current_playing_item = None

    def _set_volume(self, value):
        if self.media_player: self.media_player.audio_set_volume(value)

    def _handle_player_state_change(self, event):
        if not self.media_player: return
        new_state = self.media_player.get_state()
        print(f"VLC 状态改变: {new_state} (来自事件: {event.type})")
        state_map = {
            vlc.State.Opening: "打开中...", vlc.State.Buffering: "缓冲中...",
            vlc.State.Playing: "播放中", vlc.State.Paused: "已暂停",
            vlc.State.Stopped: "已停止", vlc.State.Ended: "已结束",
            vlc.State.Error: "错误",
        }
        status_message = state_map.get(new_state, f"未知状态 ({new_state})")
        channel_name = ""
        if self.current_playing_item:
            channel_data = self.current_playing_item.data(Qt.UserRole)
            if channel_data: channel_name = channel_data.get('name', '')
        title = "M3U 直播播放器 (列表在右)"
        full_status = status_message
        if channel_name:
            if new_state in [vlc.State.Opening, vlc.State.Buffering, vlc.State.Playing]:
                 full_status = f"{status_message}: {channel_name}"
                 title = f"正在播放: {channel_name} - M3U 直播播放器"
            elif new_state == vlc.State.Paused:
                 full_status = f"{status_message}: {channel_name}"
                 title = f"已暂停: {channel_name} - M3U 直播播放器"
            elif new_state == vlc.State.Error:
                 full_status = f"播放错误: {channel_name}"
        self.status_bar.showMessage(full_status)
        self.setWindowTitle(title)
        can_play_pause = new_state in [vlc.State.Playing, vlc.State.Paused]
        can_stop = new_state in [vlc.State.Playing, vlc.State.Paused, vlc.State.Buffering, vlc.State.Opening]
        self.play_pause_button.setEnabled(can_play_pause)
        self.stop_button.setEnabled(can_stop)
        self._update_play_pause_icon()
        if new_state in [vlc.State.Stopped, vlc.State.Ended, vlc.State.Error]:
            if self.current_playing_item:
                self.current_playing_item.setBackground(self.channel_list_widget.palette().base())
                self.current_playing_item = None

    def _update_play_pause_icon(self):
        style = self.style()
        if self.media_player and self.media_player.is_playing():
            self.play_pause_button.setIcon(style.standardIcon(QStyle.SP_MediaPause))
            self.play_pause_button.setToolTip("暂停")
        else:
            self.play_pause_button.setIcon(style.standardIcon(QStyle.SP_MediaPlay))
            self.play_pause_button.setToolTip("播放")

    def closeEvent(self, event):
        print("开始关闭窗口和释放资源...")
        self._stop_playback()
        if self.media_player:
            try:
                self.media_player.release()
                self.media_player = None
                print("VLC Media Player 已释放。")
            except Exception as e: print(f"释放 VLC Media Player 时出错: {e}")
        if self.vlc_instance:
            try:
                self.vlc_instance.release()
                self.vlc_instance = None
                print("VLC Instance 已释放。")
            except Exception as e: print(f"释放 VLC Instance 时出错: {e}")
        print("资源释放完成。")
        event.accept()

# --- 程序入口 ---
if __name__ == '__main__':
    app = QApplication(sys.argv)
    player_window = M3UPlayerWindow()
    player_window.show()
    sys.exit(app.exec_())
