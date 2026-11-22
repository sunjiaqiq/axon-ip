# -*- coding: utf-8 -*-
"""
执行进度视图
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QFrame, QTextEdit, QProgressBar)
from PyQt5.QtCore import Qt, QTimer

class ExecutionProgress(QWidget):
    def __init__(self, on_finish_callback):
        super().__init__()
        self.on_finish_callback = on_finish_callback
        self.progress = 0
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_progress)
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)
        
        # 标题
        header_layout = QHBoxLayout()
        header_left = QHBoxLayout()
        icon_label = QLabel("⚡")
        icon_label.setFixedSize(48, 48)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet("""
            background-color: #6366f1;
            border-radius: 12px;
            font-size: 24px;
        """)
        header_left.addWidget(icon_label)
        
        title_layout = QVBoxLayout()
        title = QLabel("自动化任务执行中")
        title.setStyleSheet("""
            font-size: 20px;
            font-weight: bold;
            color: white;
        """)
        subtitle = QLabel("自主管道运行中")
        subtitle.setStyleSheet("""
            font-size: 10px;
            color: #475569;
            font-weight: bold;
        """)
        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)
        header_left.addLayout(title_layout)
        
        header_layout.addLayout(header_left, 1)
        header_layout.addStretch()
        
        # 状态标签
        status_frame = QFrame()
        status_frame.setStyleSheet("""
            QFrame {
                background-color: #0f172a;
                border: none;
                border-radius: 12px;
            }
        """)
        status_layout = QHBoxLayout(status_frame)
        status_layout.setContentsMargins(16, 12, 16, 12)
        
        status_dot = QLabel("●")
        status_dot.setStyleSheet("""
            font-size: 8px;
            color: #10b981;
        """)
        status_label = QLabel("服务器: 在线")
        status_label.setStyleSheet("""
            font-size: 10px;
            color: #94a3b8;
            font-weight: bold;
        """)
        status_layout.addWidget(status_dot)
        status_layout.addWidget(status_label)
        status_layout.addSpacing(16)
        
        divider = QFrame()
        divider.setFixedWidth(1)
        divider.setStyleSheet("background-color: rgba(255, 255, 255, 0.1);")
        status_layout.addWidget(divider)
        status_layout.addSpacing(16)
        
        storage_label = QLabel("存储: 45.2 GB 可用")
        storage_label.setStyleSheet("""
            font-size: 10px;
            color: #64748b;
            font-weight: bold;
        """)
        status_layout.addWidget(storage_label)
        header_layout.addWidget(status_frame)
        
        layout.addLayout(header_layout)
        
        # 主内容区域
        content_layout = QHBoxLayout()
        
        # 左侧步骤列表
        left_widget = QWidget()
        left_widget.setFixedWidth(240)
        left_widget.setStyleSheet("""
            QWidget {
                background-color: #131720;
                border: none;
                border-radius: 16px;
            }
        """)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(24, 24, 24, 24)
        
        steps_title = QLabel("任务管道")
        steps_title.setStyleSheet("""
            font-size: 10px;
            font-weight: bold;
            color: #475569;
        """)
        left_layout.addWidget(steps_title)
        left_layout.addSpacing(16)
        
        steps = [
            ("素材生成 (3/5)", "渲染高清片段...", "active"),
            ("文案适配", "AI脚本优化中...", "waiting"),
            ("合规检测", "等待前置任务", "locked"),
            ("全局分发", "预检待处理", "locked"),
        ]
        
        for title, desc, status in steps:
            step_widget = self.create_step_widget(title, desc, status)
            left_layout.addWidget(step_widget)
        
        left_layout.addStretch()
        content_layout.addWidget(left_widget)
        
        # 中间进度区域
        center_layout = QVBoxLayout()
        center_layout.setSpacing(16)
        
        # 进度圆环
        progress_frame = QFrame()
        progress_frame.setStyleSheet("""
            QFrame {
                background-color: #131720;
                border: none;
                border-radius: 24px;
            }
        """)
        progress_layout = QVBoxLayout(progress_frame)
        progress_layout.setContentsMargins(48, 48, 48, 48)
        
        self.progress_label = QLabel("0%")
        self.progress_label.setAlignment(Qt.AlignCenter)
        self.progress_label.setStyleSheet("""
            font-size: 72px;
            font-weight: bold;
            color: white;
        """)
        progress_layout.addWidget(self.progress_label)
        
        progress_subtitle = QLabel("总体进度")
        progress_subtitle.setAlignment(Qt.AlignCenter)
        progress_subtitle.setStyleSheet("""
            font-size: 10px;
            color: #475569;
            font-weight: bold;
        """)
        progress_layout.addWidget(progress_subtitle)
        
        # 统计信息
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(48)
        
        for label, value, subvalue in [
            ("预计完成时间", "12:45", "提前02:10"),
            ("处理速度", "1.2x", "提升0.1x"),
            ("资产产出", "18 / 30", "正常输出")
        ]:
            stat_widget = QVBoxLayout()
            stat_label = QLabel(label)
            stat_label.setAlignment(Qt.AlignCenter)
            stat_label.setStyleSheet("""
                font-size: 9px;
                color: #475569;
                font-weight: bold;
            """)
            stat_value = QLabel(value)
            stat_value.setAlignment(Qt.AlignCenter)
            stat_value.setStyleSheet("""
                font-size: 20px;
                font-weight: bold;
                color: white;
            """)
            stat_subvalue = QLabel(subvalue)
            stat_subvalue.setAlignment(Qt.AlignCenter)
            stat_subvalue.setStyleSheet("""
                font-size: 10px;
                color: #f43f5e;
                font-weight: bold;
            """)
            stat_widget.addWidget(stat_label)
            stat_widget.addWidget(stat_value)
            stat_widget.addWidget(stat_subvalue)
            stats_layout.addLayout(stat_widget)
        
        progress_layout.addLayout(stats_layout)
        center_layout.addWidget(progress_frame, 1)
        
        # 日志
        log_frame = QFrame()
        log_frame.setStyleSheet("""
            QFrame {
                background-color: #131720;
                border: none;
                border-radius: 16px;
            }
        """)
        log_layout = QVBoxLayout(log_frame)
        log_layout.setContentsMargins(24, 24, 24, 24)
        
        log_title = QLabel("System_Trace_Log")
        log_title.setStyleSheet("""
            font-size: 10px;
            color: #475569;
            font-weight: bold;
        """)
        log_layout.addWidget(log_title)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFixedHeight(160)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #0b0e14;
                border: none;
                border-radius: 12px;
                color: #475569;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 10px;
                padding: 12px;
            }
        """)
        self.log_text.append("[成功] 神经网络引擎已初始化...")
        self.log_text.append("[处理] 获取文案模板...")
        log_layout.addWidget(self.log_text)
        
        center_layout.addWidget(log_frame)
        content_layout.addLayout(center_layout, 1)
        
        # 右侧操作按钮
        right_widget = QWidget()
        right_widget.setFixedWidth(56)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setSpacing(16)
        
        pause_btn = QPushButton("⏸")
        pause_btn.setFixedSize(56, 56)
        pause_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 16px;
                color: #94a3b8;
                font-size: 24px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.1);
                color: white;
            }
        """)
        right_layout.addWidget(pause_btn)
        
        stop_btn = QPushButton("⏹")
        stop_btn.setFixedSize(56, 56)
        stop_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(244, 63, 94, 0.1);
                border: 1px solid rgba(244, 63, 94, 0.3);
                border-radius: 16px;
                color: #fb7185;
                font-size: 24px;
            }
            QPushButton:hover {
                background-color: #f43f5e;
                color: white;
            }
        """)
        stop_btn.clicked.connect(self.on_stop)
        right_layout.addWidget(stop_btn)
        
        right_layout.addStretch()
        content_layout.addWidget(right_widget)
        
        layout.addLayout(content_layout)
        layout.addStretch()
        
        # 开始进度更新
        self.start_progress()
    
    def create_step_widget(self, title, desc, status):
        """创建步骤组件"""
        widget = QFrame()
        widget.setStyleSheet("background-color: transparent;")
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 8, 0, 8)
        
        # 状态点
        status_dot = QLabel("●")
        status_dot.setFixedSize(32, 32)
        status_dot.setAlignment(Qt.AlignCenter)
        if status == "active":
            status_dot.setStyleSheet("""
                background-color: #6366f1;
                border: none;
                border-radius: 16px;
                color: white;
                font-size: 16px;
            """)
        elif status == "waiting":
            status_dot.setStyleSheet("""
                background-color: #0f172a;
                border: none;
                border-radius: 16px;
                color: #818cf8;
                font-size: 16px;
            """)
        else:
            status_dot.setStyleSheet("""
                background-color: #0b0e14;
                border: none;
                border-radius: 16px;
                color: #475569;
                font-size: 16px;
            """)
        layout.addWidget(status_dot)
        
        # 文本
        text_layout = QVBoxLayout()
        title_label = QLabel(title)
        title_label.setStyleSheet("""
            font-size: 12px;
            font-weight: bold;
            color: #818cf8;
        """)
        desc_label = QLabel(desc)
        desc_label.setStyleSheet("""
            font-size: 9px;
            color: #475569;
            font-weight: bold;
        """)
        text_layout.addWidget(title_label)
        text_layout.addWidget(desc_label)
        layout.addLayout(text_layout)
        
        return widget
    
    def start_progress(self):
        """开始进度更新"""
        self.progress = 0
        self.timer.start(200)  # 每200ms更新一次
    
    def update_progress(self):
        """更新进度"""
        self.progress += 1
        if self.progress > 100:
            self.progress = 100
            self.timer.stop()
            self.log_text.append("[成功] 所有任务已完成！")
        else:
            self.progress_label.setText(f"{self.progress}%")
            if self.progress % 5 == 0:
                messages = [
                    "[处理] 生成变体...",
                    "[成功] 合规检测通过 (分数: 98/100)",
                    "[处理] 提取视频音频流...",
                    "[AI语音] 同步音频轨道",
                    "[成功] H.264 高配置文件编码完成"
                ]
                import random
                self.log_text.append(random.choice(messages))
    
    def on_stop(self):
        """停止执行"""
        self.timer.stop()
        self.on_finish_callback()

