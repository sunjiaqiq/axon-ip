# -*- coding: utf-8 -*-
"""
素材生产视图
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QGridLayout, QFrame, QDialog)
from PyQt5.QtCore import Qt

class MaterialProduction(QWidget):
    def __init__(self, on_oral_broadcast_clicked=None, on_settings_clicked=None):
        super().__init__()
        self.on_oral_broadcast_clicked = on_oral_broadcast_clicked
        self.on_settings_clicked = on_settings_clicked
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)
        
        # 标题
        header_layout = QHBoxLayout()
        header_left = QVBoxLayout()
        title = QLabel("AI生成内容系列")
        title.setStyleSheet("""
            font-size: 28px;
            font-weight: bold;
            color: white;
        """)
        subtitle = QLabel("尖端 AI 视听引擎，赋能全方位创作流")
        subtitle.setStyleSheet("""
            font-size: 14px;
            color: #94a3b8;
        """)
        header_left.addWidget(title)
        header_left.addWidget(subtitle)
        header_layout.addLayout(header_left, 1)
        layout.addLayout(header_layout)
        
        # 模块网格
        grid = QGridLayout()
        grid.setSpacing(16)
        
        # 9个模块
        modules = [
            ("口播视频", "一键生成自然流畅的口播画面与配音", "#6366f1", True),
            ("漫画创作", "将文字剧本转化为精美连环画场景", "#06b6d4", False),
            ("产品展示", "AI 生成商业级产品建模与动态展示", "#9333ea", False),
            ("虚拟数字人", "定制化 3D 角色，支持实时互动驱动", "#14b8a6", False),
            ("背景生成", "根据主题智能延伸无限风格的环境背景", "#10b981", False),
            ("风格转换", "艺术化处理现有视频，秒变赛博或古风", "#f43f5e", False),
            ("AI配音", "智能语音合成，支持多语言多音色", "#f59e0b", False),
            ("视频剪辑", "AI智能剪辑，自动生成精彩片段", "#8b5cf6", False),
            ("图片生成", "根据文字描述生成高质量图片", "#ec4899", False),
        ]
        
        for i, (title, desc, color, has_detail) in enumerate(modules):
            card = self.create_module_card(title, desc, color, has_detail)
            row = i // 3
            col = i % 3
            grid.addWidget(card, row, col)
        
        # 确保9个模块显示为3x3网格
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        
        layout.addLayout(grid)
        layout.addStretch()
        
        # 右下角设置按钮
        if self.on_settings_clicked:
            settings_btn = QPushButton("⚙️ 系统设置")
            settings_btn.setFixedSize(120, 40)
            settings_btn.setCursor(Qt.PointingHandCursor)
            settings_btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(99, 102, 241, 0.2);
                    border: 1px solid rgba(99, 102, 241, 0.3);
                    border-radius: 8px;
                    color: #818cf8;
                    font-size: 14px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: rgba(99, 102, 241, 0.3);
                    border-color: rgba(99, 102, 241, 0.5);
                }
            """)
            settings_btn.clicked.connect(self.on_settings_clicked)
            
            # 将按钮放在右下角
            footer_layout = QHBoxLayout()
            footer_layout.addStretch()
            footer_layout.addWidget(settings_btn)
            layout.addLayout(footer_layout)
    
    def create_module_card(self, title, desc, color, has_detail):
        """创建模块卡片"""
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #131720;
                border: none;
                border-radius: 24px;
            }
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(16)
        
        # 标题（居中显示，移除图标）
        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignCenter)  # 标题居中
        title_label.setStyleSheet("""
            font-size: 20px;
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
        
        # 只有口播视频有按钮
        if has_detail and self.on_oral_broadcast_clicked:
            enter_btn = QPushButton("进入")
            enter_btn.setFixedHeight(48)  # 增大按钮高度
            enter_btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(99, 102, 241, 0.1);
                    border: 1px solid rgba(99, 102, 241, 0.3);
                    border-radius: 12px;
                    padding: 12px 24px;
                    color: #818cf8;
                    font-weight: bold;
                    font-size: 16px;
                }
                QPushButton:hover {
                    background-color: #6366f1;
                    color: white;
                }
            """)
            enter_btn.clicked.connect(self.on_oral_broadcast_clicked_with_loading)
            layout.addWidget(enter_btn)
        
        return card
    
    def on_oral_broadcast_clicked_with_loading(self):
        """点击口播视频，显示启动弹窗"""
        if self.on_oral_broadcast_clicked:
            # 显示启动弹窗
            loading_dialog = QDialog(self)
            loading_dialog.setWindowTitle("启动中")
            loading_dialog.setFixedSize(300, 150)
            loading_dialog.setStyleSheet("""
                QDialog {
                    background-color: #131720;
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: 12px;
                }
            """)
            layout = QVBoxLayout(loading_dialog)
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
            
            loading_dialog.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
            loading_dialog.setModal(True)
            loading_dialog.show()
            
            # 延迟关闭弹窗并调用回调
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(500, lambda: (loading_dialog.close(), self.on_oral_broadcast_clicked()))
    
    def hex_to_rgb(self, hex_color):
        """将十六进制颜色转换为RGB字符串"""
        hex_color = hex_color.lstrip('#')
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        return f"{r},{g},{b}"

