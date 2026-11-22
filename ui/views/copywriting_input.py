# -*- coding: utf-8 -*-
"""
文案生成输入界面
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QTextEdit, QFrame)
from PyQt5.QtCore import Qt

class CopywritingInput(QWidget):
    def __init__(self, template_name, on_generate_callback, on_back_callback):
        super().__init__()
        self.template_name = template_name
        self.on_generate_callback = on_generate_callback
        self.on_back_callback = on_back_callback
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)
        
        # 标题栏
        header_layout = QHBoxLayout()
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
        header_layout.addStretch()
        
        title = QLabel(f"生成文案 - {self.template_name}")
        title.setStyleSheet("""
            font-size: 28px;
            font-weight: bold;
            color: white;
        """)
        header_layout.addWidget(title)
        header_layout.addStretch()
        layout.addLayout(header_layout)
        
        # 输入区域
        input_frame = QFrame()
        input_frame.setStyleSheet("""
            QFrame {
                background-color: #131720;
                border: none;
                border-radius: 16px;
            }
        """)
        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(24, 24, 24, 24)
        
        input_label = QLabel("请输入原始文案内容：")
        input_label.setStyleSheet("""
            font-size: 14px;
            font-weight: bold;
            color: white;
            margin-bottom: 12px;
        """)
        input_layout.addWidget(input_label)
        
        self.input_text = QTextEdit()
        self.input_text.setPlaceholderText("在这里输入您的原始文案...")
        self.input_text.setStyleSheet("""
            QTextEdit {
                background-color: #1a1f2a;
                border: none;
                border-radius: 12px;
                padding: 16px;
                color: #e2e8f0;
                font-size: 14px;
                min-height: 200px;
            }
        """)
        input_layout.addWidget(self.input_text, 1)
        
        layout.addWidget(input_frame, 1)
        
        # 输出区域
        output_frame = QFrame()
        output_frame.setStyleSheet("""
            QFrame {
                background-color: #131720;
                border: none;
                border-radius: 16px;
            }
        """)
        output_layout = QVBoxLayout(output_frame)
        output_layout.setContentsMargins(24, 24, 24, 24)
        
        output_label = QLabel("生成的文案：")
        output_label.setStyleSheet("""
            font-size: 14px;
            font-weight: bold;
            color: white;
            margin-bottom: 12px;
        """)
        output_layout.addWidget(output_label)
        
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setPlaceholderText("生成的文案将显示在这里...")
        self.output_text.setStyleSheet("""
            QTextEdit {
                background-color: #1a1f2a;
                border: none;
                border-radius: 12px;
                padding: 16px;
                color: #e2e8f0;
                font-size: 14px;
                min-height: 200px;
            }
        """)
        output_layout.addWidget(self.output_text, 1)
        
        # 复制按钮
        copy_btn = QPushButton("复制文案")
        copy_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(99, 102, 241, 0.1);
                border: 1px solid rgba(99, 102, 241, 0.3);
                border-radius: 8px;
                padding: 8px 16px;
                color: #818cf8;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #6366f1;
                color: white;
            }
        """)
        copy_btn.clicked.connect(self.copy_output)
        output_layout.addWidget(copy_btn)
        
        layout.addWidget(output_frame, 1)
        
        # 生成按钮
        generate_btn = QPushButton("生成文案")
        generate_btn.setFixedHeight(50)
        generate_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #6366f1, stop:1 #9333ea);
                color: white;
                border: none;
                border-radius: 12px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #5855eb, stop:1 #7e22ce);
            }
        """)
        generate_btn.clicked.connect(self.on_generate)
        layout.addWidget(generate_btn)
    
    def on_generate(self):
        """生成文案"""
        input_content = self.input_text.toPlainText().strip()
        if not input_content:
            self.output_text.setPlainText("请先输入原始文案内容！")
            return
        
        # 调用回调函数生成文案
        if self.on_generate_callback:
            result = self.on_generate_callback(self.template_name, input_content)
            self.output_text.setPlainText(result)
    
    def copy_output(self):
        """复制输出文案"""
        from PyQt5.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(self.output_text.toPlainText())

