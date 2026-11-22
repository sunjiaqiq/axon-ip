# -*- coding: utf-8 -*-
"""
侧边栏组件
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QLabel, 
                             QProgressBar, QFrame)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QColor, QPainter, QPen

class Sidebar(QWidget):
    view_changed = pyqtSignal(int)
    
    def __init__(self):
        super().__init__()
        self.setFixedWidth(256)
        self.setStyleSheet("""
            QWidget {
                background-color: #0f1219;
                border-right: none;
            }
        """)
        
        self.active_index = 0
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 顶部Logo区域
        header = QWidget()
        header.setFixedHeight(80)
        header.setStyleSheet("background-color: transparent;")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(24, 24, 24, 24)
        
        logo_label = QLabel("自动化全媒体创作系统")
        logo_label.setStyleSheet("""
            font-size: 20px;
            font-weight: bold;
            color: white;
            background-color: transparent;
        """)
        header_layout.addWidget(logo_label)
        
        layout.addWidget(header)
        
        # 导航菜单
        nav_layout = QVBoxLayout()
        nav_layout.setContentsMargins(16, 16, 16, 16)
        nav_layout.setSpacing(8)
        
        menu_items = [
            ("自动化模块", 0),
            ("素材生产", 1),
            ("文案生产", 2),
            ("合规检测", 3),
            ("分发平台", 4),
        ]
        
        self.menu_buttons = []
        for label, index in menu_items:
            btn = QPushButton(label)
            btn.setFixedHeight(48)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked, idx=index: self.on_menu_clicked(idx))
            self.menu_buttons.append(btn)
            nav_layout.addWidget(btn)
        
        nav_widget = QWidget()
        nav_widget.setLayout(nav_layout)
        layout.addWidget(nav_widget, 1)
        
        # 底部区域
        footer = QWidget()
        footer.setStyleSheet("""
            QWidget {
                background-color: transparent;
                border-top: none;
            }
        """)
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(16, 16, 16, 16)
        footer_layout.setSpacing(16)
        
        # 配额使用
        quota_widget = QWidget()
        quota_widget.setStyleSheet("""
            QWidget {
                background-color: rgba(15, 23, 42, 0.5);
                border: none;
                border-radius: 12px;
            }
        """)
        quota_layout = QVBoxLayout(quota_widget)
        quota_layout.setContentsMargins(16, 16, 16, 16)
        
        quota_header = QLabel("配额使用")
        quota_header.setStyleSheet("""
            font-size: 10px;
            font-weight: bold;
            color: #64748b;
            text-transform: uppercase;
            letter-spacing: 0.1em;
        """)
        quota_layout.addWidget(quota_header)
        
        quota_progress = QProgressBar()
        quota_progress.setValue(82)
        quota_progress.setStyleSheet("""
            QProgressBar {
                height: 6px;
                border: none;
                border-radius: 3px;
                background-color: #1e293b;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #6366f1, stop:1 #a855f7);
                border-radius: 3px;
            }
        """)
        quota_layout.addWidget(quota_progress)
        
        footer_layout.addWidget(quota_widget)
        
        # 设置按钮
        settings_btn = QPushButton("系统设置")
        settings_btn.setFixedHeight(48)
        settings_btn.setCursor(Qt.PointingHandCursor)
        settings_btn.clicked.connect(lambda: self.on_menu_clicked(5))
        self.menu_buttons.append(settings_btn)
        footer_layout.addWidget(settings_btn)
        
        layout.addWidget(footer)
        
        # 更新按钮样式
        self.update_button_styles()
    
    def on_menu_clicked(self, index):
        """菜单点击事件"""
        self.set_active_view(index)
        self.view_changed.emit(index)
    
    def set_active_view(self, index):
        """设置活动视图"""
        self.active_index = index
        self.update_button_styles()
    
    def update_button_styles(self):
        """更新按钮样式"""
        for i, btn in enumerate(self.menu_buttons):
            if i == self.active_index:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: rgba(99, 102, 241, 0.2);
                        color: #818cf8;
                        border: 1px solid rgba(99, 102, 241, 0.3);
                        border-radius: 12px;
                        text-align: left;
                        padding-left: 16px;
                        font-size: 14px;
                        font-weight: 500;
                    }
                    QPushButton:hover {
                        background-color: rgba(99, 102, 241, 0.25);
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: transparent;
                        color: #94a3b8;
                        border: none;
                        border-radius: 12px;
                        text-align: left;
                        padding-left: 16px;
                        font-size: 14px;
                        font-weight: 500;
                    }
                    QPushButton:hover {
                        background-color: rgba(255, 255, 255, 0.05);
                        color: #e2e8f0;
                    }
                """)

