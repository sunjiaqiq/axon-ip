# -*- coding: utf-8 -*-
"""
口播视频详细界面
"""

import os
import sys
import threading
import subprocess
import requests
from pathlib import Path
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QTextEdit, QFrame, QFileDialog,
                             QMessageBox, QProgressBar, QDialog)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtWidgets import QApplication

# API基础URL
API_BASE_URL = "http://127.0.0.1:38810"

class LoadingDialog(QDialog):
    """启动中弹窗"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("启动中")
        self.setFixedSize(300, 150)
        self.setStyleSheet("""
            QDialog {
                background-color: #131720;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 12px;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        
        label = QLabel("正在启动服务...")
        label.setStyleSheet("""
            font-size: 14px;
            color: white;
            font-weight: bold;
        """)
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setModal(True)

class StatusCheckThread(QThread):
    """后台检查连接状态的线程"""
    status_changed = pyqtSignal(bool)  # True=连接成功, False=连接失败
    
    def __init__(self):
        super().__init__()
        self.running = True
    
    def check_api_keys(self):
        """检查API Keys是否已设置"""
        try:
            import yaml
            # 使用项目根目录
            current_file = Path(__file__)
            project_root = current_file.parent.parent.parent
            config_path = project_root / "pixelle_wrapper" / "config.yaml"
            if not config_path.exists():
                return False
            
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
            
            qwen_key = config.get('llm', {}).get('api_key', '').strip()
            runninghub_key = config.get('comfyui', {}).get('runninghub_api_key', '').strip()
            
            return bool(qwen_key and runninghub_key)
        except Exception as e:
            print(f"检查API Keys失败: {e}")
            return False
    
    def run(self):
        while self.running:
            try:
                # 先检查服务是否运行（快速检查）
                try:
                    health_response = requests.get(f"{API_BASE_URL}/health", timeout=1)
                    if health_response.status_code != 200:
                        self.status_changed.emit(False)
                        self.msleep(2000)
                        continue
                except:
                    self.status_changed.emit(False)
                    self.msleep(2000)
                    continue
                
                # 检查真正的连接状态（Pixelle-Video和RunningHub，使用较短超时）
                try:
                    conn_response = requests.get(f"{API_BASE_URL}/api/connection_status", timeout=1.5)
                except requests.exceptions.Timeout:
                    # 超时不一定是连接失败，可能是服务繁忙，不改变状态，继续检查
                    # 不打印日志，避免刷屏
                    self.msleep(2000)
                    continue
                except Exception as e:
                    # 其他异常才打印日志
                    print(f"[连接检查] 连接状态检查异常: {e}")
                    self.status_changed.emit(False)
                    self.msleep(2000)
                    continue
                if conn_response.status_code == 200:
                    data = conn_response.json()
                    status = data.get("status")
                    if status == "connected":
                        print(f"[连接检查] 所有服务连接正常: {data.get('message')}")
                        self.status_changed.emit(True)
                    else:
                        # 打印连接失败的原因
                        message = data.get("message", "连接失败")
                        details = []
                        if not data.get("pixelle_available"):
                            details.append("Pixelle-Video不可用")
                        if not data.get("qwen_key_configured"):
                            details.append("通义千问Key未配置")
                        if not data.get("runninghub_key_configured"):
                            details.append("RunningHub Key未配置")
                        print(f"[连接检查] 连接未就绪: {message}")
                        if details:
                            print(f"[连接检查] 详情: {', '.join(details)}")
                        self.status_changed.emit(False)
                else:
                    print(f"[连接检查] 连接状态检查失败 (状态码: {conn_response.status_code})")
                    self.status_changed.emit(False)
            except Exception as e:
                print(f"[连接检查] 检查异常: {e}")
                self.status_changed.emit(False)
            self.msleep(2000)  # 每2秒检查一次
    
    def stop(self):
        self.running = False

class TaskStatusThread(QThread):
    """查询任务状态的线程"""
    status_updated = pyqtSignal(dict)  # 任务状态更新
    
    def __init__(self, task_id):
        super().__init__()
        self.task_id = task_id
        self.running = True
    
    def run(self):
        while self.running:
            try:
                response = requests.get(f"{API_BASE_URL}/api/task/{self.task_id}", timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    self.status_updated.emit(data)
                    if data.get("status") in ["done", "error"]:
                        break
            except Exception as e:
                print(f"查询任务状态失败: {e}")
            self.msleep(1000)  # 每秒查询一次
    
    def stop(self):
        self.running = False

class OralBroadcastDetail(QWidget):
    def __init__(self, on_back_callback):
        super().__init__()
        self.on_back_callback = on_back_callback
        self.api_base_url = API_BASE_URL
        self.avatar_path = None
        self.product_path = None
        self.audio_path = None
        self.task_id = None
        self.status_thread = None
        self.task_thread = None
        self.wrapper_process = None
        
        self.init_ui()
        
        # 不自动启动wrapper，等视图显示时再启动
        self._wrapper_started = False
        self._status_check_started = False
    
    def check_and_start_wrapper(self):
        """检查wrapper服务是否运行，如果没有则启动"""
        try:
            response = requests.get(f"{self.api_base_url}/health", timeout=2)
            if response.status_code == 200:
                print("[Wrapper] 服务已运行")
                return True
        except Exception as e:
            print(f"[Wrapper] 服务未运行: {e}")
        
        # 显示启动弹窗
        self.loading_dialog = LoadingDialog(self)
        self.loading_dialog.show()
        QApplication.processEvents()  # 确保弹窗显示
        
        # 启动wrapper服务
        def start_wrapper():
            try:
                wrapper_path = Path(__file__).parent.parent.parent / "pixelle_wrapper" / "main.py"
                if not wrapper_path.exists():
                    print(f"[Wrapper] 路径不存在: {wrapper_path}")
                    QTimer.singleShot(0, self.loading_dialog.close)
                    return
                
                print(f"[Wrapper] 正在启动服务: {wrapper_path}")
                
                # 使用subprocess启动wrapper，输出到控制台以便查看日志
                # 注意：在Windows上，如果使用CREATE_NO_WINDOW，日志会被重定向，看不到
                # 这里改为显示窗口，或者使用文件输出
                import sys
                if sys.platform == 'win32':
                    # Windows: 创建一个新的控制台窗口显示日志
                    self.wrapper_process = subprocess.Popen(
                        [sys.executable, str(wrapper_path)],
                        creationflags=subprocess.CREATE_NEW_CONSOLE  # 创建新控制台窗口
                    )
                else:
                    # Linux/Mac: 直接输出到当前控制台
                    self.wrapper_process = subprocess.Popen(
                        [sys.executable, str(wrapper_path)]
                    )
                
                # 等待服务启动
                import time
                for i in range(30):  # 最多等待30秒
                    time.sleep(1)
                    try:
                        response = requests.get(f"{self.api_base_url}/health", timeout=1)
                        if response.status_code == 200:
                            print("[Wrapper] 服务启动成功")
                            QTimer.singleShot(0, self.loading_dialog.close)
                            return
                    except:
                        pass
                    if i % 5 == 0:
                        print(f"[Wrapper] 等待服务启动... ({i}/30)")
                
                print("[Wrapper] 服务启动超时")
                QTimer.singleShot(0, self.loading_dialog.close)
            except Exception as e:
                print(f"[Wrapper] 启动失败: {e}")
                import traceback
                traceback.print_exc()
                QTimer.singleShot(0, self.loading_dialog.close)
        
        thread = threading.Thread(target=start_wrapper, daemon=True)
        thread.start()
    
    def start_status_check(self):
        """启动连接状态检查"""
        self.status_thread = StatusCheckThread()
        self.status_thread.status_changed.connect(self.update_connection_status)
        self.status_thread.start()
    
    def update_connection_status(self, connected):
        """更新连接状态指示器"""
        if hasattr(self, 'status_indicator'):
            if connected:
                self.status_indicator.setStyleSheet("""
                    QLabel {
                        background-color: #10b981;
                        border-radius: 6px;
                        min-width: 12px;
                        max-width: 12px;
                        min-height: 12px;
                        max-height: 12px;
                    }
                """)
                print("[UI] 连接状态: 已连接 (绿点)")
            else:
                self.status_indicator.setStyleSheet("""
                    QLabel {
                        background-color: #ef4444;
                        border-radius: 6px;
                        min-width: 12px;
                        max-width: 12px;
                        min-height: 12px;
                        max-height: 12px;
                    }
                """)
                print("[UI] 连接状态: 未连接 (红点)")
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        # 缩小20%：从32改为26，从24改为19
        layout.setContentsMargins(26, 26, 26, 26)
        layout.setSpacing(19)
        
        # 标题栏
        header_layout = QHBoxLayout()
        header_left = QVBoxLayout()
        title = QLabel("口播视频生成")
        title.setStyleSheet("""
            font-size: 22px;
            font-weight: bold;
            color: white;
        """)
        header_left.addWidget(title)
        header_layout.addLayout(header_left, 1)
        
        # 连接状态指示器和API Key设置
        status_layout = QHBoxLayout()
        status_layout.setSpacing(8)
        self.status_indicator = QLabel()
        self.status_indicator.setFixedSize(12, 12)
        self.status_indicator.setStyleSheet("""
            QLabel {
                background-color: #ef4444;
                border-radius: 6px;
            }
        """)
        status_layout.addWidget(self.status_indicator)
        status_label = QLabel("连接状态")
        status_label.setStyleSheet("""
            font-size: 10px;
            color: #94a3b8;
        """)
        status_layout.addWidget(status_label)
        
        # API Key设置按钮
        api_key_btn = QPushButton("设置API Key")
        api_key_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(99, 102, 241, 0.2);
                border: 1px solid rgba(99, 102, 241, 0.5);
                border-radius: 6px;
                padding: 4px 12px;
                color: #818cf8;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(99, 102, 241, 0.4);
                color: #a5b4fc;
            }
        """)
        api_key_btn.clicked.connect(self.on_set_api_keys)
        status_layout.addWidget(api_key_btn)
        
        header_layout.addLayout(status_layout)
        
        back_btn = QPushButton("← 返回")
        back_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 12px;
                padding: 10px 20px;
                color: #94a3b8;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.1);
                color: white;
            }
        """)
        back_btn.clicked.connect(self.on_back_callback)
        header_layout.addWidget(back_btn)
        layout.addLayout(header_layout)
        
        # 主内容区域
        content_layout = QHBoxLayout()
        content_layout.setSpacing(19)  # 缩小20%
        
        # 左侧上传区域
        left_layout = QVBoxLayout()
        left_layout.setSpacing(13)  # 缩小20%
        left_layout.setContentsMargins(0, 0, 0, 0)  # 确保没有额外边距
        
        # 人物视觉素材
        self.person_frame = self.create_upload_frame("人物视觉素材", "", "上传人物图片", "avatar")
        left_layout.addWidget(self.person_frame, 0)  # stretch=0，不占用额外空间
        
        # 产品视觉素材
        self.product_frame = self.create_upload_frame("产品视觉素材", "", "上传产品图片", "product")
        left_layout.addWidget(self.product_frame, 0)  # stretch=0，不占用额外空间
        
        # 音频驱动源（使用相同的create_upload_frame，保持界面一致）
        self.audio_frame = self.create_upload_frame("音频驱动源", "", "上传音频", "audio")
        left_layout.addWidget(self.audio_frame, 0)  # stretch=0，不占用额外空间
        
        content_layout.addLayout(left_layout, 0)  # stretch=0，确保不挤压其他元素
        
        # 右侧脚本区域
        script_frame = QFrame()
        script_frame.setStyleSheet("""
            QFrame {
                background-color: #131720;
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 16px;
            }
        """)
        script_layout = QVBoxLayout(script_frame)
        script_layout.setContentsMargins(19, 19, 19, 19)  # 缩小20%
        
        script_header = QHBoxLayout()
        script_icon = QLabel("📄")
        script_icon.setFixedSize(40, 40)
        script_icon.setAlignment(Qt.AlignCenter)
        script_icon.setStyleSheet("""
            background-color: rgba(16, 185, 129, 0.1);
            border: 1px solid rgba(16, 185, 129, 0.2);
            border-radius: 8px;
            font-size: 20px;
        """)
        script_header.addWidget(script_icon)
        
        script_title = QLabel("脚本提示词")
        script_title.setStyleSheet("""
            font-size: 16px;
            font-weight: bold;
            color: white;
        """)
        script_header.addWidget(script_title)
        script_header.addStretch()
        script_layout.addLayout(script_header)
        
        self.script_input = QTextEdit()
        self.script_input.setPlaceholderText("请输入视频生成的提示词或文案内容...")
        self.script_input.setStyleSheet("""
            QTextEdit {
                background-color: #1a1f2a;
                border: none;
                border-radius: 12px;
                padding: 13px;
                color: #cbd5e1;
                font-size: 11px;
            }
        """)
        script_layout.addWidget(self.script_input, 1)
        
        # 进度条
        progress_layout = QHBoxLayout()
        self.progress_label = QLabel("系统就绪")
        self.progress_label.setStyleSheet("""
            font-size: 10px;
            color: #818cf8;
            font-weight: bold;
        """)
        progress_layout.addWidget(self.progress_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #1e293b;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background-color: #0ea5e9;
                border-radius: 2px;
            }
        """)
        progress_layout.addWidget(self.progress_bar, 1)
        
        self.progress_value = QLabel("进度: 0%")
        self.progress_value.setStyleSheet("""
            font-size: 10px;
            color: #64748b;
            font-weight: bold;
        """)
        progress_layout.addWidget(self.progress_value)
        script_layout.addLayout(progress_layout)
        
        # 生成按钮
        self.generate_btn = QPushButton("▶ 执行生成")
        self.generate_btn.setFixedHeight(38)
        self.generate_btn.setStyleSheet("""
            QPushButton {
                background-color: #0ea5e9;
                color: #0f172a;
                border: none;
                border-radius: 12px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #38bdf8;
            }
            QPushButton:disabled {
                background-color: #475569;
                color: #64748b;
            }
        """)
        self.generate_btn.clicked.connect(self.on_generate)
        script_layout.addWidget(self.generate_btn)
        
        content_layout.addWidget(script_frame, 1)
        layout.addLayout(content_layout)
        
        # 输出区域（确保可见）
        output_frame = QFrame()
        output_frame.setMinimumHeight(100)  # 确保最小高度，可见
        output_frame.setStyleSheet("""
            QFrame {
                background-color: #131720;
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 16px;
            }
        """)
        output_layout = QVBoxLayout(output_frame)
        output_layout.setContentsMargins(19, 19, 19, 19)  # 缩小20%
        
        output_label = QLabel("生成的输出链接")
        output_label.setStyleSheet("""
            font-size: 10px;
            font-weight: bold;
            color: #64748b;
        """)
        output_layout.addWidget(output_label)
        
        url_layout = QHBoxLayout()
        self.url_label = QLabel("等待生成...")
        self.url_label.setStyleSheet("""
            background-color: #0b0e14;
            border: none;
            border-radius: 12px;
            padding: 10px;
            color: #94a3b8;
            font-family: monospace;
            font-size: 10px;
        """)
        url_layout.addWidget(self.url_label, 1)
        
        self.copy_btn = QPushButton("复制")
        self.copy_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 6px 13px;
                color: #64748b;
                font-size: 10px;
            }
            QPushButton:hover {
                color: white;
            }
            QPushButton:disabled {
                color: #475569;
            }
        """)
        self.copy_btn.clicked.connect(self.on_copy_url)
        self.copy_btn.setEnabled(False)
        url_layout.addWidget(self.copy_btn)
        output_layout.addLayout(url_layout)
        
        # 确保输出区域始终可见，添加到布局末尾
        layout.addWidget(output_frame, 0)  # stretch=0，不占用额外空间，但保持可见
    
    def create_upload_frame(self, title, desc, btn_text, file_type):
        """创建上传框架"""
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #131720;
                border: none;
                border-radius: 16px;
            }
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(20, 20, 20, 20)  # 进一步缩小边距，避免重叠
        layout.setSpacing(8)  # 设置间距
        layout.setAlignment(Qt.AlignCenter)
        
        # 根据文件类型选择不同的图标
        if file_type == "audio":
            icon_text = "🎤"
            icon_bg = "rgba(147, 51, 234, 0.1)"
            icon_border = "rgba(147, 51, 234, 0.2)"
        else:
            icon_text = "📷"
            icon_bg = "rgba(99, 102, 241, 0.1)"
            icon_border = "rgba(99, 102, 241, 0.2)"
        
        icon = QLabel(icon_text)
        icon.setFixedSize(38, 38)  # 缩小20%
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet(f"""
            background-color: {icon_bg};
            border: 1px solid {icon_border};
            border-radius: 8px;
            font-size: 24px;
        """)
        layout.addWidget(icon)
        
        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("""
            font-size: 11px;
            font-weight: bold;
            color: white;
            margin-top: 10px;
        """)
        layout.addWidget(title_label)
        
        # 如果有描述文字才显示（现在为空，不显示）
        if desc:
            desc_label = QLabel(desc)
            desc_label.setAlignment(Qt.AlignCenter)
            desc_label.setStyleSheet("""
                font-size: 10px;
                color: #64748b;
                font-weight: bold;
                margin-bottom: 16px;
            """)
            layout.addWidget(desc_label)
        
        # 去掉黑框（upload_area），直接添加按钮，缩小40%
        upload_btn = QPushButton(btn_text)
        upload_btn.setFixedHeight(19)  # 缩小40%：从32缩小到19
        upload_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(99, 102, 241, 0.2);
                border: 1px solid rgba(99, 102, 241, 0.5);
                border-radius: 8px;
                color: #818cf8;
                font-size: 10px;
                font-weight: bold;
                padding: 4px 12px;
            }
            QPushButton:hover {
                background-color: rgba(99, 102, 241, 0.4);
                border: 1px solid rgba(99, 102, 241, 0.8);
                color: #a5b4fc;
            }
            QPushButton:pressed {
                background-color: rgba(99, 102, 241, 0.6);
            }
        """)
        # 根据文件类型选择不同的文件过滤器
        if file_type == "audio":
            file_filter = "音频文件 (*.mp3 *.wav *.m4a)"
        else:
            file_filter = "图片文件 (*.png *.jpg *.jpeg)"
        upload_btn.clicked.connect(lambda checked, ft=file_type, ff=file_filter: self.select_file(ff, ft))
        layout.addWidget(upload_btn)  # 直接添加到主布局，按钮往上移
        
        # 上传状态提示（显示上传成功/失败）
        status_label = QLabel("")
        status_label.setAlignment(Qt.AlignCenter)
        status_label.setStyleSheet("""
            font-size: 9px;
            color: #10b981;
            font-weight: bold;
            margin-top: 4px;
            min-height: 14px;
        """)
        status_label.hide()  # 初始隐藏
        layout.addWidget(status_label)
        
        # 保存状态标签和按钮引用
        if file_type == "avatar":
            self.avatar_status_label = status_label
            self.avatar_upload_btn = upload_btn
        elif file_type == "product":
            self.product_status_label = status_label
            self.product_upload_btn = upload_btn
        elif file_type == "audio":
            self.audio_status_label = status_label
            self.audio_btn = upload_btn  # 保持audio_btn的引用名，兼容现有代码
        
        return frame
    
    def select_file(self, file_filter, file_type):
        """选择文件并上传"""
        file_path, _ = QFileDialog.getOpenFileName(self, "选择文件", "", file_filter)
        if not file_path:
            return
        
        # 显示上传中
        if file_type == "avatar":
            self.avatar_upload_btn.setText("上传中...")
            self.avatar_upload_btn.setEnabled(False)
            if hasattr(self, 'avatar_status_label'):
                self.avatar_status_label.hide()
        elif file_type == "product":
            self.product_upload_btn.setText("上传中...")
            self.product_upload_btn.setEnabled(False)
            if hasattr(self, 'product_status_label'):
                self.product_status_label.hide()
        elif file_type == "audio":
            self.audio_btn.setText("上传中...")
            self.audio_btn.setEnabled(False)
        
        # 在后台线程中上传
        def upload_file():
            try:
                if file_type == "avatar":
                    url = f"{self.api_base_url}/api/avatar"
                    print(f"[上传] 开始上传人物图片: {file_path}")
                    with open(file_path, 'rb') as f:
                        files = {'file': (os.path.basename(file_path), f)}
                        response = requests.post(url, files=files, timeout=30)
                    print(f"[上传] 人物图片上传响应: {response.status_code}")
                    if response.status_code == 200:
                        self.avatar_path = file_path
                        print(f"[上传] 人物图片上传成功")
                        # 使用QTimer在主线程中更新UI，使用functools.partial避免闭包问题
                        from functools import partial
                        QTimer.singleShot(0, partial(self._update_upload_status, "avatar", True, "✓ 上传成功"))
                    else:
                        print(f"[上传] 人物图片上传失败: {response.status_code}, {response.text}")
                        from functools import partial
                        QTimer.singleShot(0, partial(self._update_upload_status, "avatar", False, "✗ 上传失败"))
                elif file_type == "product":
                    url = f"{self.api_base_url}/api/product"
                    print(f"[上传] 开始上传产品图片: {file_path}")
                    with open(file_path, 'rb') as f:
                        files = {'file': (os.path.basename(file_path), f)}
                        response = requests.post(url, files=files, timeout=30)
                    print(f"[上传] 产品图片上传响应: {response.status_code}")
                    if response.status_code == 200:
                        self.product_path = file_path
                        print(f"[上传] 产品图片上传成功")
                        from functools import partial
                        QTimer.singleShot(0, partial(self._update_upload_status, "product", True, "✓ 上传成功"))
                    else:
                        print(f"[上传] 产品图片上传失败: {response.status_code}, {response.text}")
                        from functools import partial
                        QTimer.singleShot(0, partial(self._update_upload_status, "product", False, "✗ 上传失败"))
                elif file_type == "audio":
                    url = f"{self.api_base_url}/api/audio"
                    print(f"[上传] 开始上传音频: {file_path}")
                    with open(file_path, 'rb') as f:
                        files = {'file': (os.path.basename(file_path), f)}
                        response = requests.post(url, files=files, timeout=30)
                    print(f"[上传] 音频上传响应: {response.status_code}")
                    if response.status_code == 200:
                        self.audio_path = file_path
                        print(f"[上传] 音频上传成功")
                        from functools import partial
                        QTimer.singleShot(0, partial(self._update_upload_status, "audio", True, "✓ 上传成功"))
                    else:
                        print(f"[上传] 音频上传失败: {response.status_code}, {response.text}")
                        from functools import partial
                        QTimer.singleShot(0, partial(self._update_upload_status, "audio", False, "✗ 上传失败"))
            except Exception as e:
                print(f"[上传] 上传文件异常: {e}")
                import traceback
                traceback.print_exc()
                # 所有类型都更新按钮状态
                from functools import partial
                if file_type == "avatar":
                    QTimer.singleShot(0, partial(self._update_upload_status, "avatar", False, "✗ 上传失败"))
                    QTimer.singleShot(100, partial(QMessageBox.warning, self, "错误", f"上传人物图片失败: {str(e)}"))
                elif file_type == "product":
                    QTimer.singleShot(0, partial(self._update_upload_status, "product", False, "✗ 上传失败"))
                    QTimer.singleShot(100, partial(QMessageBox.warning, self, "错误", f"上传产品图片失败: {str(e)}"))
                elif file_type == "audio":
                    QTimer.singleShot(0, partial(self._update_upload_status, "audio", False, "✗ 上传失败"))
        
        thread = threading.Thread(target=upload_file, daemon=True)
        thread.start()
    
    def _update_upload_status(self, file_type, success, message):
        """在主线程中更新上传状态（避免线程问题）"""
        if file_type == "avatar":
            if hasattr(self, 'avatar_upload_btn'):
                self.avatar_upload_btn.setText("上传人物图片")
                self.avatar_upload_btn.setEnabled(True)
                # 按钮状态反馈：成功显示绿色，失败显示红色
                if success:
                    self.avatar_upload_btn.setStyleSheet("""
                        QPushButton {
                            background-color: rgba(16, 185, 129, 0.2);
                            border: 1px solid rgba(16, 185, 129, 0.6);
                            border-radius: 8px;
                            padding: 8px 16px;
                            color: #10b981;
                            font-size: 12px;
                            font-weight: bold;
                        }
                        QPushButton:hover {
                            background-color: rgba(16, 185, 129, 0.3);
                            border: 1px solid rgba(16, 185, 129, 0.8);
                        }
                    """)
                else:
                    self.avatar_upload_btn.setStyleSheet("""
                        QPushButton {
                            background-color: rgba(147, 51, 234, 0.3);
                            border: 1px solid rgba(147, 51, 234, 0.6);
                            border-radius: 8px;
                            padding: 8px 16px;
                            color: white;
                            font-size: 12px;
                            font-weight: bold;
                        }
                        QPushButton:hover {
                            background-color: rgba(147, 51, 234, 0.5);
                            border: 1px solid rgba(147, 51, 234, 0.8);
                        }
                    """)
            if hasattr(self, 'avatar_status_label'):
                self.avatar_status_label.setText(message)
                color = "#10b981" if success else "#ef4444"
                self.avatar_status_label.setStyleSheet(f"""
                    font-size: 10px;
                    color: {color};
                    font-weight: bold;
                    margin-top: 4px;
                    min-height: 16px;
                """)
                self.avatar_status_label.show()
        elif file_type == "product":
            if hasattr(self, 'product_upload_btn'):
                self.product_upload_btn.setText("上传产品图片")
                self.product_upload_btn.setEnabled(True)
                # 按钮状态反馈：成功显示绿色，失败显示红色
                if success:
                    self.product_upload_btn.setStyleSheet("""
                        QPushButton {
                            background-color: rgba(16, 185, 129, 0.2);
                            border: 1px solid rgba(16, 185, 129, 0.6);
                            border-radius: 8px;
                            padding: 8px 16px;
                            color: #10b981;
                            font-size: 12px;
                            font-weight: bold;
                        }
                        QPushButton:hover {
                            background-color: rgba(16, 185, 129, 0.3);
                            border: 1px solid rgba(16, 185, 129, 0.8);
                        }
                    """)
                else:
                    self.product_upload_btn.setStyleSheet("""
                        QPushButton {
                            background-color: rgba(147, 51, 234, 0.3);
                            border: 1px solid rgba(147, 51, 234, 0.6);
                            border-radius: 8px;
                            padding: 8px 16px;
                            color: white;
                            font-size: 12px;
                            font-weight: bold;
                        }
                        QPushButton:hover {
                            background-color: rgba(147, 51, 234, 0.5);
                            border: 1px solid rgba(147, 51, 234, 0.8);
                        }
                    """)
            if hasattr(self, 'product_status_label'):
                self.product_status_label.setText(message)
                color = "#10b981" if success else "#ef4444"
                self.product_status_label.setStyleSheet(f"""
                    font-size: 10px;
                    color: {color};
                    font-weight: bold;
                    margin-top: 4px;
                    min-height: 16px;
                """)
                self.product_status_label.show()
        elif file_type == "audio":
            if hasattr(self, 'audio_btn'):
                self.audio_btn.setText("上传音频")
                self.audio_btn.setEnabled(True)
                # 按钮状态反馈：成功显示绿色，失败显示红色
                if success:
                    self.audio_btn.setStyleSheet("""
                        QPushButton {
                            background-color: rgba(16, 185, 129, 0.2);
                            border: 1px solid rgba(16, 185, 129, 0.6);
                            border-radius: 8px;
                            padding: 8px 16px;
                            color: #10b981;
                            font-size: 12px;
                            font-weight: bold;
                        }
                        QPushButton:hover {
                            background-color: rgba(16, 185, 129, 0.3);
                            border: 1px solid rgba(16, 185, 129, 0.8);
                        }
                    """)
                else:
                    self.audio_btn.setStyleSheet("""
                        QPushButton {
                            background-color: rgba(147, 51, 234, 0.3);
                            border: 1px solid rgba(147, 51, 234, 0.6);
                            border-radius: 8px;
                            padding: 8px 16px;
                            color: white;
                            font-size: 12px;
                            font-weight: bold;
                        }
                        QPushButton:hover {
                            background-color: rgba(147, 51, 234, 0.5);
                            border: 1px solid rgba(147, 51, 234, 0.8);
                        }
                    """)
            if hasattr(self, 'audio_status_label'):
                self.audio_status_label.setText(message)
                color = "#10b981" if success else "#ef4444"
                self.audio_status_label.setStyleSheet(f"""
                    font-size: 9px;
                    color: {color};
                    font-weight: bold;
                    margin-top: 4px;
                    min-height: 14px;
                """)
                self.audio_status_label.show()
    
    def on_set_api_keys(self):
        """设置API Keys（通义千问和RunningHub）"""
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QHBoxLayout
        
        # 读取当前配置
        qwen_key = ""
        runninghub_key = ""
        try:
            import yaml
            config_path = Path(__file__).parent.parent.parent / "pixelle_wrapper" / "config.yaml"
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    if config:
                        qwen_key = config.get('llm', {}).get('api_key', '')
                        runninghub_key = config.get('comfyui', {}).get('runninghub_api_key', '')
        except:
            pass
        
        # 创建对话框
        dialog = QDialog(self)
        dialog.setWindowTitle("设置API Key")
        dialog.setFixedSize(500, 250)
        dialog.setStyleSheet("""
            QDialog {
                background-color: #131720;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 12px;
            }
            QLabel {
                color: white;
                font-size: 12px;
            }
            QLineEdit {
                background-color: #1a1f2a;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 6px;
                padding: 8px;
                color: white;
                font-size: 11px;
            }
            QPushButton {
                background-color: rgba(99, 102, 241, 0.3);
                border: 1px solid rgba(99, 102, 241, 0.5);
                border-radius: 6px;
                padding: 8px 16px;
                color: #818cf8;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(99, 102, 241, 0.5);
            }
        """)
        
        layout = QVBoxLayout(dialog)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)
        
        # 通义千问Key
        qwen_label = QLabel("通义千问 API Key:")
        layout.addWidget(qwen_label)
        qwen_input = QLineEdit()
        qwen_input.setText(qwen_key)
        qwen_input.setPlaceholderText("请输入通义千问API Key")
        layout.addWidget(qwen_input)
        
        # RunningHub Key
        runninghub_label = QLabel("RunningHub API Key:")
        layout.addWidget(runninghub_label)
        runninghub_input = QLineEdit()
        runninghub_input.setText(runninghub_key)
        runninghub_input.setPlaceholderText("请输入RunningHub API Key")
        layout.addWidget(runninghub_input)
        
        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel_btn)
        ok_btn = QPushButton("确定")
        ok_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(ok_btn)
        layout.addLayout(btn_layout)
        
        if dialog.exec_() == QDialog.Accepted:
            new_qwen_key = qwen_input.text().strip()
            new_runninghub_key = runninghub_input.text().strip()
            
            if not new_qwen_key or not new_runninghub_key:
                QMessageBox.warning(self, "错误", "两个API Key都必须填写！")
                return
            
            try:
                # 保存到config.yaml
                import yaml
                config_path = Path(__file__).parent.parent.parent / "pixelle_wrapper" / "config.yaml"
                config = {}
                if config_path.exists():
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config = yaml.safe_load(f) or {}
                
                if 'llm' not in config:
                    config['llm'] = {}
                if 'comfyui' not in config:
                    config['comfyui'] = {}
                
                config['llm']['api_key'] = new_qwen_key
                config['comfyui']['runninghub_api_key'] = new_runninghub_key
                
                with open(config_path, 'w', encoding='utf-8') as f:
                    yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
                
                # 设置通义千问Key到wrapper
                response = requests.post(
                    f"{self.api_base_url}/api/set_key",
                    json={"api_key": new_qwen_key},
                    timeout=5
                )
                
                if response.status_code == 200:
                    QMessageBox.information(self, "成功", "API Keys已设置并保存")
                else:
                    QMessageBox.warning(self, "错误", "设置API Key失败")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"设置API Key失败: {str(e)}")
    
    def check_api_keys(self):
        """检查API Keys是否已设置"""
        try:
            import yaml
            config_path = Path(__file__).parent.parent.parent / "pixelle_wrapper" / "config.yaml"
            if not config_path.exists():
                return False, "配置文件不存在"
            
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
            
            qwen_key = config.get('llm', {}).get('api_key', '').strip()
            runninghub_key = config.get('comfyui', {}).get('runninghub_api_key', '').strip()
            
            if not qwen_key:
                return False, "通义千问API Key未设置"
            if not runninghub_key:
                return False, "RunningHub API Key未设置"
            
            return True, "API Keys已配置"
        except Exception as e:
            return False, f"检查API Key失败: {str(e)}"
    
    def on_generate(self):
        """执行生成"""
        script = self.script_input.toPlainText().strip()
        if not script:
            QMessageBox.warning(self, "提示", "请输入脚本提示词")
            return
        
        # 检查真正的连接状态（Pixelle-Video和RunningHub）
        try:
            # 先检查服务是否运行
            health_response = requests.get(f"{self.api_base_url}/health", timeout=2)
            if health_response.status_code != 200:
                QMessageBox.warning(self, "错误", "服务未连接，请检查服务状态")
                return
            
            # 检查真正的连接状态
            conn_response = requests.get(f"{self.api_base_url}/api/connection_status", timeout=3)
            if conn_response.status_code == 200:
                data = conn_response.json()
                if data.get("status") != "connected":
                    message = data.get("message", "连接失败")
                    details = []
                    if not data.get("pixelle_available"):
                        details.append("Pixelle-Video 不可用")
                    if not data.get("qwen_key_configured"):
                        details.append("通义千问 API Key 未配置")
                    if not data.get("runninghub_key_configured"):
                        details.append("RunningHub API Key 未配置")
                    
                    error_msg = f"{message}\n\n"
                    if details:
                        error_msg += "详情：\n" + "\n".join(f"- {d}" for d in details)
                    error_msg += "\n\n请点击'设置API Key'按钮进行配置，或检查wrapper服务日志"
                    
                    QMessageBox.warning(self, "连接未就绪", error_msg)
                    return
                else:
                    print(f"[生成] 连接状态检查通过: {data.get('message')}")
            else:
                QMessageBox.warning(self, "错误", "无法检查连接状态")
                return
        except Exception as e:
            QMessageBox.warning(self, "错误", f"无法连接到服务: {str(e)}\n\n请确保服务已启动")
            return
        
        # 显示启动弹窗
        self.loading_dialog = LoadingDialog(self)
        self.loading_dialog.show()
        
        # 在后台线程中执行生成
        def generate():
            try:
                # 1. 设置文案
                response = requests.post(
                    f"{self.api_base_url}/api/text",
                    json={"text": script},
                    timeout=10
                )
                if response.status_code != 200:
                    raise Exception("设置文案失败")
                
                # 2. 开始生成
                response = requests.post(
                    f"{self.api_base_url}/api/generate",
                    timeout=10
                )
                if response.status_code != 200:
                    raise Exception("启动生成失败")
                
                data = response.json()
                self.task_id = data.get("task_id")
                
                # 关闭启动弹窗
                self.loading_dialog.close()
                
                # 开始查询任务状态
                self.task_thread = TaskStatusThread(self.task_id)
                self.task_thread.status_updated.connect(self.on_task_status_updated)
                self.task_thread.start()
                
                # 更新UI
                self.generate_btn.setEnabled(False)
                self.progress_label.setText("生成中...")
                
            except Exception as e:
                self.loading_dialog.close()
                QMessageBox.critical(self, "错误", f"生成失败: {str(e)}")
                self.generate_btn.setEnabled(True)
        
        thread = threading.Thread(target=generate, daemon=True)
        thread.start()
    
    def on_task_status_updated(self, status_data):
        """任务状态更新回调"""
        status = status_data.get("status")
        progress = status_data.get("progress", 0)
        output = status_data.get("output")
        error = status_data.get("error")
        
        # 更新进度条
        self.progress_bar.setValue(progress)
        self.progress_value.setText(f"进度: {progress}%")
        
        if status == "done":
            self.progress_label.setText("生成完成")
            self.progress_bar.setValue(100)
            self.generate_btn.setEnabled(True)
            
            # 显示输出路径
            if output:
                self.url_label.setText(output)
                self.copy_btn.setEnabled(True)
            
            # 停止查询线程
            if self.task_thread:
                self.task_thread.stop()
                self.task_thread = None
                
        elif status == "error":
            self.progress_label.setText(f"生成失败: {error}")
            self.generate_btn.setEnabled(True)
            
            # 停止查询线程
            if self.task_thread:
                self.task_thread.stop()
                self.task_thread = None
    
    def on_copy_url(self):
        """复制URL到剪贴板"""
        url = self.url_label.text()
        if url and url != "等待生成...":
            clipboard = QApplication.clipboard()
            clipboard.setText(url)
            QMessageBox.information(self, "提示", "已复制到剪贴板")
    
    def showEvent(self, event):
        """视图显示时启动wrapper和状态检查"""
        super().showEvent(event)
        if not self._wrapper_started:
            self._wrapper_started = True
            # 检查并启动wrapper服务（在视图显示时）
            QTimer.singleShot(100, self.check_and_start_wrapper)
        
        if not self._status_check_started:
            self._status_check_started = True
            # 延迟启动状态检查，确保UI已初始化
            QTimer.singleShot(500, self.start_status_check)
    
    def closeEvent(self, event):
        """关闭时清理资源"""
        # 停止状态检查线程
        if self.status_thread:
            self.status_thread.stop()
            self.status_thread.wait(1000)  # 最多等待1秒
        
        # 停止任务查询线程
        if self.task_thread:
            self.task_thread.stop()
            self.task_thread.wait(1000)  # 最多等待1秒
        
        # 关闭wrapper进程
        if self.wrapper_process:
            try:
                print("[UI] 正在停止wrapper服务...")
                self.wrapper_process.terminate()
                try:
                    self.wrapper_process.wait(timeout=3)
                    print("[UI] wrapper服务已正常停止")
                except subprocess.TimeoutExpired:
                    print("[UI] wrapper服务未响应，强制终止...")
                    self.wrapper_process.kill()
                    self.wrapper_process.wait()
                    print("[UI] wrapper服务已强制终止")
            except Exception as e:
                print(f"[UI] 停止wrapper服务时出错: {e}")
                try:
                    self.wrapper_process.kill()
                except:
                    pass
        
        event.accept()
