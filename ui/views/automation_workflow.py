# -*- coding: utf-8 -*-
"""
自动化工作流视图
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QComboBox, QCheckBox, QPushButton, QFrame, QTextEdit)
from PyQt5.QtCore import Qt

class AutomationWorkflow(QWidget):
    def __init__(self, config, on_start_callback):
        super().__init__()
        self.config = config
        self.on_start_callback = on_start_callback
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)
        
        # 标题
        header = QVBoxLayout()
        title = QLabel("工作流配置")
        title.setStyleSheet("""
            font-size: 28px;
            font-weight: bold;
            color: white;
        """)
        subtitle = QLabel("自动化内容创作全链路编排")
        subtitle.setStyleSheet("""
            font-size: 14px;
            color: #94a3b8;
        """)
        header.addWidget(title)
        header.addWidget(subtitle)
        layout.addLayout(header)
        
        # 主内容区域
        content_layout = QHBoxLayout()
        
        # 左侧配置区域
        left_layout = QVBoxLayout()
        left_layout.setSpacing(16)
        
        # 步骤1: 文案策划模型
        step1 = self.create_step_widget(
            "01", "文案策划模型", "AI 智能脚本生成模板选择",
            "copywritingTemplate", ["爆款钩子 (Hook) 模型", "情感共鸣深度叙事", "产品评测专业对比"]
        )
        left_layout.addWidget(step1)
        
        # 步骤2: 合规监测
        step2 = self.create_compliance_widget()
        left_layout.addWidget(step2)
        
        # 步骤3: 素材生产模块
        step3 = self.create_step_widget(
            "03", "素材生产模块", "视听渲染引擎与素材组合方式",
            "materialModule", ["AI 真人口播", "漫画创作矩阵", "虚拟数字人"]
        )
        left_layout.addWidget(step3)
        
        # 步骤4: 分发平台
        step4 = self.create_platforms_widget()
        left_layout.addWidget(step4)
        
        # 开始按钮
        start_btn = QPushButton("一键开启自动化生成")
        start_btn.setFixedHeight(60)
        start_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #6366f1, stop:1 #9333ea);
                color: white;
                border: none;
                border-radius: 16px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #5855eb, stop:1 #7e22ce);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4f46e5, stop:1 #6b21a8);
            }
        """)
        start_btn.clicked.connect(self.on_start)
        left_layout.addWidget(start_btn)
        
        content_layout.addLayout(left_layout, 2)
        
        # 右侧状态区域
        right_widget = QWidget()
        right_widget.setFixedWidth(300)
        right_widget.setStyleSheet("""
            QWidget {
                background-color: #131720;
                border: none;
                border-radius: 24px;
            }
        """)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(32, 32, 32, 32)
        
        # 状态圆环
        status_label = QLabel("空闲")
        status_label.setAlignment(Qt.AlignCenter)
        status_label.setStyleSheet("""
            font-size: 48px;
            font-weight: bold;
            color: white;
        """)
        right_layout.addWidget(status_label)
        
        status_subtitle = QLabel("核心引擎\n等待输入...")
        status_subtitle.setAlignment(Qt.AlignCenter)
        status_subtitle.setStyleSheet("""
            font-size: 12px;
            color: #64748b;
            font-weight: bold;
        """)
        right_layout.addWidget(status_subtitle)
        
        right_layout.addStretch()
        
        # 控制台
        console = QTextEdit()
        console.setReadOnly(True)
        console.setFixedHeight(200)
        console.setStyleSheet("""
            QTextEdit {
                background-color: #0b0e14;
                border: none;
                border-radius: 12px;
                color: #64748b;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 10px;
                padding: 12px;
            }
        """)
        console.append("[SYSTEM] Initialization complete...")
        console.append("[SYSTEM] Ready for workflow configuration...")
        console.append("[INFO] All nodes reporting healthy.")
        right_layout.addWidget(console)
        
        content_layout.addWidget(right_widget)
        layout.addLayout(content_layout)
        layout.addStretch()
    
    def create_step_widget(self, step_num, title, desc, config_key, options):
        """创建步骤组件"""
        widget = QFrame()
        widget.setStyleSheet("""
            QFrame {
                background-color: #131720;
                border: none;
                border-radius: 16px;
            }
        """)
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(24, 24, 24, 24)
        
        # 步骤编号
        num_label = QLabel(step_num)
        num_label.setFixedSize(40, 40)
        num_label.setAlignment(Qt.AlignCenter)
        num_label.setStyleSheet("""
            background-color: rgba(99, 102, 241, 0.1);
            color: #818cf8;
            border: 1px solid rgba(99, 102, 241, 0.2);
            border-radius: 8px;
            font-weight: bold;
        """)
        layout.addWidget(num_label)
        
        # 内容区域
        content_layout = QVBoxLayout()
        content_layout.setSpacing(4)
        
        title_label = QLabel(title)
        title_label.setStyleSheet("""
            font-size: 16px;
            font-weight: 600;
            color: white;
        """)
        content_layout.addWidget(title_label)
        
        desc_label = QLabel(desc)
        desc_label.setStyleSheet("""
            font-size: 12px;
            color: #64748b;
        """)
        content_layout.addWidget(desc_label)
        
        layout.addLayout(content_layout, 1)
        
        # 下拉框
        combo = QComboBox()
        combo.addItems(options)
        combo.setCurrentText(self.config.get(config_key, options[0]))
        combo.currentTextChanged.connect(lambda text: self.config.update({config_key: text}))
        combo.setStyleSheet("""
            QComboBox {
                background-color: #1a1f2a;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 8px 16px;
                color: #cbd5e1;
                min-width: 180px;
            }
            QComboBox:hover {
                border-color: #6366f1;
            }
            QComboBox::drop-down {
                border: none;
            }
        """)
        layout.addWidget(combo)
        
        return widget
    
    def create_compliance_widget(self):
        """创建合规监测组件"""
        widget = QFrame()
        widget.setStyleSheet("""
            QFrame {
                background-color: #131720;
                border: none;
                border-radius: 16px;
            }
        """)
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(24, 24, 24, 24)
        
        # 步骤编号
        num_label = QLabel("02")
        num_label.setFixedSize(40, 40)
        num_label.setAlignment(Qt.AlignCenter)
        num_label.setStyleSheet("""
            background-color: rgba(16, 185, 129, 0.1);
            color: #34d399;
            border: 1px solid rgba(16, 185, 129, 0.2);
            border-radius: 8px;
            font-weight: bold;
        """)
        layout.addWidget(num_label)
        
        # 内容区域
        content_layout = QVBoxLayout()
        content_layout.setSpacing(4)
        
        title_label = QLabel("全自动合规监测")
        title_label.setStyleSheet("""
            font-size: 16px;
            font-weight: 600;
            color: white;
        """)
        content_layout.addWidget(title_label)
        
        desc_label = QLabel("敏感词库实时检测与风控拦截")
        desc_label.setStyleSheet("""
            font-size: 12px;
            color: #64748b;
        """)
        content_layout.addWidget(desc_label)
        
        layout.addLayout(content_layout, 1)
        
        # 开关
        checkbox = QCheckBox()
        checkbox.setChecked(self.config.get('complianceEnabled', True))
        checkbox.toggled.connect(lambda checked: self.config.update({'complianceEnabled': checked}))
        checkbox.setStyleSheet("""
            QCheckBox::indicator {
                width: 44px;
                height: 24px;
                border-radius: 12px;
                background-color: #475569;
            }
            QCheckBox::indicator:checked {
                background-color: #10b981;
            }
        """)
        layout.addWidget(checkbox)
        
        return widget
    
    def create_platforms_widget(self):
        """创建平台选择组件"""
        widget = QFrame()
        widget.setStyleSheet("""
            QFrame {
                background-color: #131720;
                border: none;
                border-radius: 16px;
            }
        """)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(24, 24, 24, 24)
        
        # 步骤编号和标题
        header_layout = QHBoxLayout()
        num_label = QLabel("04")
        num_label.setFixedSize(40, 40)
        num_label.setAlignment(Qt.AlignCenter)
        num_label.setStyleSheet("""
            background-color: rgba(244, 63, 94, 0.1);
            color: #fb7185;
            border: 1px solid rgba(244, 63, 94, 0.2);
            border-radius: 8px;
            font-weight: bold;
        """)
        header_layout.addWidget(num_label)
        
        title_label = QLabel("全平台分发配置")
        title_label.setStyleSheet("""
            font-size: 16px;
            font-weight: 600;
            color: white;
        """)
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        layout.addLayout(header_layout)
        
        # 平台按钮
        platforms_layout = QHBoxLayout()
        platforms = [
            ("douyin", "Douyin"),
            ("xhs", "XHS"),
            ("shipinhao", "WeChat"),
            ("bilibili", "Bilibili")
        ]
        
        self.platform_buttons = {}
        for platform_id, platform_name in platforms:
            btn = QPushButton(platform_name)
            btn.setCheckable(True)
            btn.setChecked(platform_id in self.config.get('platforms', []))
            btn.toggled.connect(lambda checked, pid=platform_id: self.toggle_platform(pid, checked))
            btn.setStyleSheet("""
                QPushButton {
                    padding: 8px 24px;
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: 12px;
                    background-color: rgba(255, 255, 255, 0.05);
                    color: #64748b;
                    font-size: 10px;
                    font-weight: bold;
                }
                QPushButton:checked {
                    background-color: rgba(244, 63, 94, 0.2);
                    border-color: rgba(244, 63, 94, 0.5);
                    color: #fb7185;
                }
                QPushButton:hover {
                    border-color: rgba(255, 255, 255, 0.2);
                }
            """)
            self.platform_buttons[platform_id] = btn
            platforms_layout.addWidget(btn)
        
        layout.addLayout(platforms_layout)
        
        return widget
    
    def toggle_platform(self, platform_id, checked):
        """切换平台选择"""
        platforms = self.config.get('platforms', [])
        if checked and platform_id not in platforms:
            platforms.append(platform_id)
        elif not checked and platform_id in platforms:
            platforms.remove(platform_id)
        self.config['platforms'] = platforms
    
    def on_start(self):
        """开始自动化"""
        self.on_start_callback(self.config)

