# -*- coding: utf-8 -*-
"""
文案生产视图
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QGridLayout, QFrame, QLineEdit)
from PyQt5.QtCore import Qt

class CopywritingProduction(QWidget):
    def __init__(self, on_template_clicked=None):
        super().__init__()
        self.on_template_clicked = on_template_clicked
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)
        
        # 标题和搜索
        header_layout = QHBoxLayout()
        header_left = QVBoxLayout()
        title = QLabel("爆款文案生产矩阵")
        title.setStyleSheet("""
            font-size: 28px;
            font-weight: bold;
            color: white;
        """)
        subtitle = QLabel("预设专业 AI 模板，加速病毒式内容创作。")
        subtitle.setStyleSheet("""
            font-size: 14px;
            color: #94a3b8;
        """)
        header_left.addWidget(title)
        header_left.addWidget(subtitle)
        header_layout.addLayout(header_left, 1)
        
        # 搜索框和按钮
        search_layout = QHBoxLayout()
        search_input = QLineEdit()
        search_input.setPlaceholderText("搜索模板...")
        search_input.setFixedWidth(256)
        search_input.setStyleSheet("""
            QLineEdit {
                background-color: #0f172a;
                border: none;
                border-radius: 12px;
                padding: 10px 16px;
                color: #cbd5e1;
            }
        """)
        custom_btn = QPushButton("自定义提示")
        custom_btn.setStyleSheet("""
            QPushButton {
                background-color: #6366f1;
                color: white;
                border: none;
                border-radius: 12px;
                padding: 10px 24px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5855eb;
            }
        """)
        search_layout.addWidget(search_input)
        search_layout.addWidget(custom_btn)
        header_layout.addLayout(search_layout)
        
        layout.addLayout(header_layout)
        
        # 模板网格
        grid = QGridLayout()
        grid.setSpacing(16)
        
        templates = [
            ("爆款钩子", "黄金3秒钩子，瞬间抓住用户注意力，降低跳出率。"),
            ("故事脚本", "包含起承转合的完整叙事逻辑，适用于剧情及Vlog。"),
            ("产品评测", "挖掘产品痛点与卖点，客观专业的种草与避雷指南。"),
            ("标题生成器", "基于心理学触发机制，批量产出让人欲罢不能的标题。"),
            ("短视频金句", "高度浓缩的情感或金句，引发用户评论区疯狂互动。"),
            ("直播话术", "涵盖欢迎、留人、逼单等全流程，打造高GMV直播间。"),
            ("小红书种草", "沉浸式体验描写，完全契合小红书社区调性。"),
            ("视频大纲", "长视频必选。清晰的主线逻辑，防止创作跑题。"),
            ("情感共鸣", "扎心或治愈系文案，深入用户灵魂，获得高互动。"),
        ]
        
        for i, (title, desc) in enumerate(templates):
            card = self.create_template_card(title, desc)
            row = i // 3
            col = i % 3
            grid.addWidget(card, row, col)
        
        layout.addLayout(grid)
        layout.addStretch()
    
    def create_template_card(self, title, desc):
        """创建模板卡片"""
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #131720;
                border: none;
                border-radius: 24px;
            }
        """)
        # 设置卡片不可点击（只有按钮可点击）
        card.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        
        # 顶部区域
        top_layout = QHBoxLayout()
        icon = QLabel("📝")
        icon.setFixedSize(48, 48)
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("""
            background-color: rgba(99, 102, 241, 0.1);
            border: none;
            border-radius: 12px;
        """)
        top_layout.addWidget(icon)
        top_layout.addStretch()
        
        # 右上角按钮
        generate_btn = QPushButton("生成文案")
        generate_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(99, 102, 241, 0.1);
                border: 1px solid rgba(99, 102, 241, 0.3);
                border-radius: 8px;
                padding: 6px 12px;
                color: #818cf8;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #6366f1;
                color: white;
            }
        """)
        if self.on_template_clicked:
            generate_btn.clicked.connect(lambda checked, t=title: self.on_template_clicked(t))
        top_layout.addWidget(generate_btn)
        layout.addLayout(top_layout)
        
        # 标题
        title_label = QLabel(title)
        title_label.setStyleSheet("""
            font-size: 16px;
            font-weight: bold;
            color: white;
        """)
        layout.addWidget(title_label)
        
        # 描述
        desc_label = QLabel(desc)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("""
            font-size: 13px;
            color: #64748b;
            line-height: 1.6;
        """)
        layout.addWidget(desc_label)
        
        layout.addStretch()
        
        return card

