# -*- coding: utf-8 -*-
"""
分发中心视图
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QGridLayout, QFrame)
from PyQt5.QtCore import Qt

class DistributionCenter(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)
        
        # 标题
        header_layout = QHBoxLayout()
        header_left = QVBoxLayout()
        title = QLabel("多平台分发中心")
        title.setStyleSheet("""
            font-size: 28px;
            font-weight: bold;
            color: white;
        """)
        subtitle = QLabel("管理您的账号矩阵，实现内容一键全网分发")
        subtitle.setStyleSheet("""
            font-size: 14px;
            color: #94a3b8;
        """)
        header_left.addWidget(title)
        header_left.addWidget(subtitle)
        header_layout.addLayout(header_left, 1)
        
        execute_btn = QPushButton("执行全平台分发")
        execute_btn.setStyleSheet("""
            QPushButton {
                background-color: #6366f1;
                color: white;
                border: none;
                border-radius: 12px;
                padding: 12px 32px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5855eb;
            }
        """)
        header_layout.addWidget(execute_btn)
        layout.addLayout(header_layout)
        
        # 平台网格
        grid = QGridLayout()
        grid.setSpacing(16)
        
        platforms = [
            ("抖音", "潮流生活家", True),
            ("快手", "创意短视频人", True),
            ("小红书", "未授权", False),
            ("视频号", "AI 视界", True),
            ("百家号", "全能创作者", True),
            ("知乎", "科技前沿观察", True),
            ("B站", "硬核AI实验室", True),
        ]
        
        for i, (name, account, connected) in enumerate(platforms):
            card = self.create_platform_card(name, account, connected)
            row = i // 4
            col = i % 4
            grid.addWidget(card, row, col)
        
        layout.addLayout(grid)
        layout.addStretch()
    
    def create_platform_card(self, name, account, connected):
        """创建平台卡片"""
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #131720;
                border: none;
                border-radius: 16px;
            }
            QFrame:hover {
                background-color: rgba(255, 255, 255, 0.05);
            }
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        
        # 顶部区域
        top_layout = QHBoxLayout()
        icon = QLabel("📱")
        icon.setFixedSize(48, 48)
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("""
            background-color: rgba(255, 255, 255, 0.05);
            border: none;
            border-radius: 12px;
        """)
        top_layout.addWidget(icon)
        top_layout.addStretch()
        
        status_label = QLabel("已登录" if connected else "未登录")
        status_label.setStyleSheet(f"""
            background-color: {'rgba(16, 185, 129, 0.1)' if connected else '#475569'};
            color: {'#34d399' if connected else '#94a3b8'};
            border-radius: 4px;
            padding: 4px 8px;
            font-size: 8px;
            font-weight: bold;
        """)
        top_layout.addWidget(status_label)
        layout.addLayout(top_layout)
        
        # 平台名称
        name_label = QLabel(name)
        name_label.setStyleSheet("""
            font-size: 18px;
            font-weight: bold;
            color: white;
        """)
        layout.addWidget(name_label)
        
        # 账号名称
        account_label = QLabel(account)
        account_label.setStyleSheet("""
            font-size: 10px;
            color: #475569;
            font-weight: bold;
        """)
        layout.addWidget(account_label)
        
        layout.addStretch()
        
        # 登录按钮（所有平台都有）
        login_btn = QPushButton("登录" if not connected else "已登录")
        login_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(99, 102, 241, 0.1);
                color: #818cf8;
                border: 1px solid rgba(99, 102, 241, 0.3);
                border-radius: 8px;
                padding: 10px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #6366f1;
                color: white;
            }
        """)
        if connected:
            login_btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(16, 185, 129, 0.1);
                    color: #34d399;
                    border: 1px solid rgba(16, 185, 129, 0.3);
                    border-radius: 8px;
                    padding: 10px;
                    font-size: 12px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: rgba(16, 185, 129, 0.2);
                }
            """)
        layout.addWidget(login_btn)
        
        layout.addStretch()
        
        return card

