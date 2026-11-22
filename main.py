#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Creator OS - 自动化全媒体创作系统
PyQt5 桌面版
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
current_dir = Path(__file__).parent.absolute()
sys.path.insert(0, str(current_dir))

from PyQt5.QtWidgets import QApplication, QMainWindow, QStackedWidget
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QColor, QPalette

from ui.main_window import MainWindow

def main():
    app = QApplication(sys.argv)
    
    # 设置应用样式
    app.setStyle('Fusion')
    
    # 设置深色主题
    dark_palette = QPalette()
    dark_palette.setColor(QPalette.Window, QColor(11, 14, 20))
    dark_palette.setColor(QPalette.WindowText, Qt.white)
    dark_palette.setColor(QPalette.Base, QColor(19, 23, 32))
    dark_palette.setColor(QPalette.AlternateBase, QColor(26, 31, 42))
    dark_palette.setColor(QPalette.ToolTipBase, Qt.white)
    dark_palette.setColor(QPalette.ToolTipText, Qt.white)
    dark_palette.setColor(QPalette.Text, Qt.white)
    dark_palette.setColor(QPalette.Button, QColor(19, 23, 32))
    dark_palette.setColor(QPalette.ButtonText, Qt.white)
    dark_palette.setColor(QPalette.BrightText, Qt.red)
    dark_palette.setColor(QPalette.Link, QColor(99, 102, 241))
    dark_palette.setColor(QPalette.Highlight, QColor(99, 102, 241))
    dark_palette.setColor(QPalette.HighlightedText, Qt.black)
    app.setPalette(dark_palette)
    
    # 设置字体
    font = QFont("Microsoft YaHei UI", 9)
    app.setFont(font)
    
    # 创建主窗口
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()

