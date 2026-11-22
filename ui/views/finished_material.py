# -*- coding: utf-8 -*-
"""
成品素材视图
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QTextEdit, QLineEdit, QFrame)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
try:
    from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
    from PyQt5.QtMultimediaWidgets import QVideoWidget
    MULTIMEDIA_AVAILABLE = True
except ImportError:
    MULTIMEDIA_AVAILABLE = False
    QMediaPlayer = None
    QMediaContent = None
    QVideoWidget = None
import os
from pathlib import Path

class FinishedMaterial(QWidget):
    """成品素材视图"""
    
    # 信号：当内容更新时发出
    content_updated = pyqtSignal(dict)  # 传递 {cover_text, title, description}
    
    def __init__(self, video_path=None, script_text=""):
        super().__init__()
        self.video_path = video_path
        self.script_text = script_text
        self.init_ui()
    
    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)
        
        # 左侧：输入框区域
        left_layout = QVBoxLayout()
        left_layout.setSpacing(20)
        
        # 1. 封面内容
        cover_frame = self.create_input_section("封面内容", "4-8个字总结", max_length=10)
        self.cover_input = cover_frame.findChild(QLineEdit)
        left_layout.addWidget(cover_frame)
        
        # 2. 标题
        title_frame = self.create_input_section("标题", "15个字总结，包含3个左右话题#", max_length=30)
        self.title_input = title_frame.findChild(QLineEdit)
        left_layout.addWidget(title_frame)
        
        # 3. 描述内容
        desc_frame = self.create_text_section("描述内容", "20字左右", max_length=50)
        self.desc_input = desc_frame.findChild(QTextEdit)
        left_layout.addWidget(desc_frame)
        
        # AI生成按钮
        ai_generate_btn = QPushButton("🤖 AI生成内容")
        ai_generate_btn.setFixedHeight(48)
        ai_generate_btn.setStyleSheet("""
            QPushButton {
                background-color: #6366f1;
                color: white;
                border: none;
                border-radius: 12px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5855eb;
            }
        """)
        ai_generate_btn.clicked.connect(self.on_ai_generate)
        left_layout.addWidget(ai_generate_btn)
        
        # 发布按钮
        publish_btn = QPushButton("📤 发布到抖音")
        publish_btn.setFixedHeight(48)
        publish_btn.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
                color: white;
                border: none;
                border-radius: 12px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #059669;
            }
        """)
        publish_btn.clicked.connect(self.on_publish)
        left_layout.addWidget(publish_btn)
        
        left_layout.addStretch()
        
        # 右侧：视频播放区域
        right_layout = QVBoxLayout()
        
        video_label = QLabel("生成视频")
        video_label.setStyleSheet("""
            font-size: 18px;
            font-weight: bold;
            color: white;
            margin-bottom: 12px;
        """)
        right_layout.addWidget(video_label)
        
        # 视频播放框
        video_frame = QFrame()
        video_frame.setStyleSheet("""
            QFrame {
                background-color: #131720;
                border: 2px solid rgba(255, 255, 255, 0.1);
                border-radius: 16px;
            }
        """)
        video_layout = QVBoxLayout(video_frame)
        video_layout.setContentsMargins(0, 0, 0, 0)
        
        # 视频播放器
        if MULTIMEDIA_AVAILABLE:
            self.video_widget = QVideoWidget()
            self.video_widget.setMinimumSize(640, 360)
            self.video_widget.setStyleSheet("""
                QVideoWidget {
                    background-color: #0a0d14;
                    border-radius: 12px;
                }
            """)
            self.media_player = QMediaPlayer()
            self.media_player.setVideoOutput(self.video_widget)
            video_layout.addWidget(self.video_widget)
        else:
            # 如果没有多媒体支持，显示占位符
            placeholder = QLabel("视频播放器\n（需要安装PyQt5多媒体支持）")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("""
                QLabel {
                    background-color: #0a0d14;
                    border-radius: 12px;
                    color: #64748b;
                    font-size: 14px;
                }
            """)
            placeholder.setMinimumSize(640, 360)
            video_layout.addWidget(placeholder)
            self.video_widget = None
            self.media_player = None
        
        # 播放控制按钮
        control_layout = QHBoxLayout()
        control_layout.setContentsMargins(12, 12, 12, 12)
        
        self.play_btn = QPushButton("▶ 播放")
        self.play_btn.setFixedHeight(40)
        self.play_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(99, 102, 241, 0.2);
                color: #818cf8;
                border: 1px solid rgba(99, 102, 241, 0.3);
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(99, 102, 241, 0.3);
            }
        """)
        self.play_btn.clicked.connect(self.toggle_play)
        control_layout.addWidget(self.play_btn)
        
        control_layout.addStretch()
        video_layout.addLayout(control_layout)
        
        right_layout.addWidget(video_frame)
        right_layout.addStretch()
        
        # 添加到主布局
        layout.addLayout(left_layout, 1)
        layout.addLayout(right_layout, 1)
        
        # 如果有视频路径，加载视频
        if self.video_path and os.path.exists(self.video_path):
            self.load_video(self.video_path)
    
    def create_input_section(self, title, placeholder, max_length=50):
        """创建输入框区域"""
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #131720;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 12px;
            }
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        
        # 标题
        title_label = QLabel(title)
        title_label.setStyleSheet("""
            font-size: 14px;
            font-weight: bold;
            color: white;
        """)
        layout.addWidget(title_label)
        
        # 输入框
        input_field = QLineEdit()
        input_field.setPlaceholderText(placeholder)
        input_field.setMaxLength(max_length)
        input_field.setStyleSheet("""
            QLineEdit {
                background-color: #0a0d14;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 12px;
                color: white;
                font-size: 14px;
            }
            QLineEdit:focus {
                border-color: #6366f1;
            }
        """)
        input_field.textChanged.connect(self.on_content_changed)
        layout.addWidget(input_field)
        
        return frame
    
    def create_text_section(self, title, placeholder, max_length=200):
        """创建文本区域"""
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #131720;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 12px;
            }
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        
        # 标题
        title_label = QLabel(title)
        title_label.setStyleSheet("""
            font-size: 14px;
            font-weight: bold;
            color: white;
        """)
        layout.addWidget(title_label)
        
        # 文本输入框
        text_input = QTextEdit()
        text_input.setPlaceholderText(placeholder)
        text_input.setMaximumHeight(100)
        text_input.setStyleSheet("""
            QTextEdit {
                background-color: #0a0d14;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 12px;
                color: white;
                font-size: 14px;
            }
            QTextEdit:focus {
                border-color: #6366f1;
            }
        """)
        text_input.textChanged.connect(self.on_content_changed)
        layout.addWidget(text_input)
        
        return frame
    
    def load_video(self, video_path):
        """加载视频文件"""
        if MULTIMEDIA_AVAILABLE and self.media_player and os.path.exists(video_path):
            self.video_path = video_path
            media_content = QMediaContent(QMediaContent.fromLocalFile(video_path))
            self.media_player.setMedia(media_content)
    
    def toggle_play(self):
        """切换播放/暂停"""
        if MULTIMEDIA_AVAILABLE and self.media_player:
            if self.media_player.state() == QMediaPlayer.PlayingState:
                self.media_player.pause()
                self.play_btn.setText("▶ 播放")
            else:
                self.media_player.play()
                self.play_btn.setText("⏸ 暂停")
    
    def on_content_changed(self):
        """内容改变时发出信号"""
        content = {
            'cover_text': self.cover_input.text() if self.cover_input else '',
            'title': self.title_input.text() if self.title_input else '',
            'description': self.desc_input.toPlainText() if self.desc_input else ''
        }
        self.content_updated.emit(content)
    
    def on_ai_generate(self):
        """AI生成内容"""
        if not self.script_text:
            # 如果没有文案，显示提示
            from PyQt5.QtWidgets import QMessageBox
            msg = QMessageBox(self)
            msg.setWindowTitle("提示")
            msg.setText("请先提供文案内容")
            msg.exec_()
            return
        
        # 调用AI生成
        self.generate_with_ai(self.script_text)
    
    def generate_with_ai(self, script_text):
        """使用AI生成封面内容、标题、描述"""
        try:
            # 导入AI生成模块
            import sys
            from pathlib import Path
            wrapper_dir = Path(__file__).parent.parent.parent / "pixelle_wrapper"
            if str(wrapper_dir) not in sys.path:
                sys.path.insert(0, str(wrapper_dir))
            
            from ai_pipeline.script_rewriter import generate_douyin_content
            
            # 生成内容
            result = generate_douyin_content(script_text)
            
            # 更新输入框
            if self.cover_input:
                self.cover_input.setText(result.get('cover_text', ''))
            if self.title_input:
                self.title_input.setText(result.get('title', ''))
            if self.desc_input:
                self.desc_input.setPlainText(result.get('description', ''))
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"AI生成失败: {e}")
            # 如果AI生成失败，使用简单规则生成
            self.generate_simple(script_text)
    
    def generate_simple(self, script_text):
        """简单规则生成（备用方案）"""
        # 封面内容：取前4-8个字
        cover_text = script_text[:8] if len(script_text) >= 8 else script_text
        if self.cover_input:
            self.cover_input.setText(cover_text)
        
        # 标题：取前15个字 + 话题
        title = script_text[:15] if len(script_text) >= 15 else script_text
        topics = ["#热门话题", "#生活分享", "#知识科普"]
        title_with_topics = f"{title} {''.join(topics)}"
        if self.title_input:
            self.title_input.setText(title_with_topics)
        
        # 描述：取前20个字
        description = script_text[:20] if len(script_text) >= 20 else script_text
        if self.desc_input:
            self.desc_input.setPlainText(description)
    
    def get_publish_content(self):
        """获取发布内容（供发布脚本使用）"""
        return {
            'cover_text': self.cover_input.text() if self.cover_input else '',
            'title': self.title_input.text() if self.title_input else '',
            'description': self.desc_input.toPlainText() if self.desc_input else '',
            'video_path': self.video_path
        }
    
    def set_video_path(self, video_path):
        """设置视频路径"""
        self.video_path = video_path
        if video_path and os.path.exists(video_path):
            self.load_video(video_path)
    
    def set_script_text(self, script_text):
        """设置文案文本"""
        self.script_text = script_text
    
    def on_publish(self):
        """发布到抖音"""
        content = self.get_publish_content()
        
        if not content.get('video_path'):
            from PyQt5.QtWidgets import QMessageBox
            msg = QMessageBox(self)
            msg.setWindowTitle("提示")
            msg.setText("请先设置视频路径")
            msg.exec_()
            return
        
        if not content.get('title'):
            from PyQt5.QtWidgets import QMessageBox
            msg = QMessageBox(self)
            msg.setWindowTitle("提示")
            msg.setText("请先填写标题")
            msg.exec_()
            return
        
        # 调用发布API
        try:
            import requests
            import json
            
            # 构建请求数据
            publish_data = {
                "video_path": content['video_path'],
                "title": content['title'],
                "description": content['description'],
                "cover_text": content['cover_text']
            }
            
            # 发送请求
            response = requests.post(
                "http://127.0.0.1:38810/api/publish/douyin",
                json=publish_data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                from PyQt5.QtWidgets import QMessageBox
                msg = QMessageBox(self)
                msg.setWindowTitle("发布成功")
                msg.setText(f"发布请求已提交：{result.get('message', '成功')}")
                msg.exec_()
            else:
                from PyQt5.QtWidgets import QMessageBox
                msg = QMessageBox(self)
                msg.setWindowTitle("发布失败")
                msg.setText(f"发布失败：{response.text}")
                msg.exec_()
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"发布失败: {e}")
            from PyQt5.QtWidgets import QMessageBox
            msg = QMessageBox(self)
            msg.setWindowTitle("发布失败")
            msg.setText(f"发布失败：{str(e)}")
            msg.exec_()

