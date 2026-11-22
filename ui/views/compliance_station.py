# -*- coding: utf-8 -*-
"""
合规检测视图
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QTextEdit, QFrame, QProgressBar)
from PyQt5.QtCore import Qt

class ComplianceStation(QWidget):
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
        title = QLabel("AI 文案合规监测站")
        title.setStyleSheet("""
            font-size: 28px;
            font-weight: bold;
            color: white;
        """)
        subtitle = QLabel("基于深度学习引擎的实时合规性与风险拦截系统")
        subtitle.setStyleSheet("""
            font-size: 14px;
            color: #94a3b8;
        """)
        header_left.addWidget(title)
        header_left.addWidget(subtitle)
        header_layout.addLayout(header_left, 1)
        
        status_badge = QLabel("引擎: v4.2.0-安全")
        status_badge.setStyleSheet("""
            background-color: rgba(16, 185, 129, 0.1);
            border: 1px solid rgba(16, 185, 129, 0.2);
            border-radius: 12px;
            padding: 8px 16px;
            color: #34d399;
            font-size: 10px;
            font-weight: bold;
        """)
        header_layout.addWidget(status_badge)
        layout.addLayout(header_layout)
        
        # 主内容区域
        content_layout = QHBoxLayout()
        
        # 左侧输入区域
        left_layout = QVBoxLayout()
        left_layout.setSpacing(16)
        
        # 输入框
        input_frame = QFrame()
        input_frame.setStyleSheet("""
            QFrame {
                background-color: #131720;
                border: none;
                border-radius: 16px;
            }
        """)
        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(0, 0, 0, 0)
        
        # 输入框头部
        input_header = QFrame()
        input_header.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 0.02);
                border-bottom: none;
            }
        """)
        input_header_layout = QHBoxLayout(input_header)
        input_header_layout.setContentsMargins(24, 16, 24, 16)
        header_label = QLabel("输入脚本内容")
        header_label.setStyleSheet("""
            font-size: 12px;
            font-weight: bold;
            color: #94a3b8;
        """)
        input_header_layout.addWidget(header_label)
        input_header_layout.addStretch()
        limit_label = QLabel("限制: 2000字")
        limit_label.setStyleSheet("""
            font-size: 9px;
            color: #475569;
        """)
        input_header_layout.addWidget(limit_label)
        input_layout.addWidget(input_header)
        
        # 文本输入
        text_input = QTextEdit()
        text_input.setPlaceholderText("请粘贴或输入您需要检测的文案内容...")
        text_input.setStyleSheet("""
            QTextEdit {
                background-color: transparent;
                border: none;
                color: #e2e8f0;
                font-size: 16px;
                padding: 32px;
            }
        """)
        input_layout.addWidget(text_input, 1)
        
        # 输入框底部
        input_footer = QFrame()
        input_footer.setStyleSheet("""
            QFrame {
                border-top: none;
            }
        """)
        input_footer_layout = QHBoxLayout(input_footer)
        input_footer_layout.setContentsMargins(24, 16, 24, 16)
        input_footer_layout.addStretch()
        
        detect_btn = QPushButton("运行检测")
        detect_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #6366f1, stop:1 #9333ea);
                color: white;
                border: none;
                border-radius: 12px;
                padding: 12px 32px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #5855eb, stop:1 #7e22ce);
            }
        """)
        input_footer_layout.addWidget(detect_btn)
        input_layout.addWidget(input_footer)
        
        left_layout.addWidget(input_frame, 1)
        content_layout.addLayout(left_layout, 2)
        
        # 右侧分析区域
        right_layout = QVBoxLayout()
        right_layout.setSpacing(16)
        
        # 风险分析卡片
        risk_card = QFrame()
        risk_card.setStyleSheet("""
            QFrame {
                background-color: #131720;
                border: none;
                border-radius: 16px;
            }
        """)
        risk_layout = QVBoxLayout(risk_card)
        risk_layout.setContentsMargins(24, 24, 24, 24)
        
        risk_title = QLabel("风险分析")
        risk_title.setStyleSheet("""
            font-size: 10px;
            font-weight: bold;
            color: #818cf8;
        """)
        risk_layout.addWidget(risk_title)
        
        # 健康分数
        score_label = QLabel("98")
        score_label.setAlignment(Qt.AlignCenter)
        score_label.setStyleSheet("""
            font-size: 48px;
            font-weight: bold;
            color: white;
            padding: 20px;
        """)
        risk_layout.addWidget(score_label)
        
        score_subtitle = QLabel("健康分数\n安全")
        score_subtitle.setAlignment(Qt.AlignCenter)
        score_subtitle.setStyleSheet("""
            font-size: 9px;
            color: #64748b;
            font-weight: bold;
        """)
        risk_layout.addWidget(score_subtitle)
        
        # 风险指标
        risk_layout.addSpacing(16)
        for label, value, percent in [("金融风险", "无", 15), 
                                       ("禁用词汇", "严重", 85),
                                       ("平台封禁", "安全", 5)]:
            item_layout = QVBoxLayout()
            item_header = QHBoxLayout()
            item_label = QLabel(label)
            item_label.setStyleSheet("""
                font-size: 9px;
                font-weight: bold;
                color: #64748b;
            """)
            item_value = QLabel(value)
            item_value.setStyleSheet("""
                font-size: 9px;
                font-weight: bold;
                color: #34d399;
            """)
            item_header.addWidget(item_label)
            item_header.addStretch()
            item_header.addWidget(item_value)
            item_layout.addLayout(item_header)
            
            progress = QProgressBar()
            progress.setValue(percent)
            progress.setFixedHeight(4)
            progress.setStyleSheet("""
                QProgressBar {
                    border: none;
                    border-radius: 2px;
                    background-color: #1e293b;
                }
                QProgressBar::chunk {
                    background-color: #10b981;
                    border-radius: 2px;
                }
            """)
            item_layout.addWidget(progress)
            risk_layout.addLayout(item_layout)
        
        right_layout.addWidget(risk_card)
        right_layout.addStretch()
        
        content_layout.addLayout(right_layout)
        layout.addLayout(content_layout)
        layout.addStretch()

