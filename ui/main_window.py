# -*- coding: utf-8 -*-
"""
主窗口
"""

from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QStackedWidget, QPushButton, QLabel)
from PyQt5.QtCore import Qt

from ui.views.material_production import MaterialProduction
from ui.views.oral_broadcast_detail import OralBroadcastDetail
from ui.views.settings import Settings
from ui.views.finished_material import FinishedMaterial

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI生成内容系列")
        self.setGeometry(100, 100, 1400, 800)
        # 允许调整窗口大小
        self.setMinimumSize(1000, 700)
        
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局：左侧边栏 + 右侧内容
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 左侧边栏
        sidebar = self.create_sidebar()
        main_layout.addWidget(sidebar)
        
        # 右侧内容区域
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        
        # 使用堆叠窗口管理视图切换
        self.stacked_widget = QStackedWidget()
        content_layout.addWidget(self.stacked_widget)
        
        # 创建各个视图
        self.material_view = MaterialProduction(self.on_oral_broadcast_clicked, self.on_settings_clicked)
        self.oral_broadcast_view = OralBroadcastDetail(self.on_back_from_oral)
        self.settings_view = Settings(self.on_back_from_settings)
        self.finished_material_view = FinishedMaterial()  # 成品素材视图
        
        # 保存settings_view的引用，供其他模块访问输出路径
        self._settings_instance = self.settings_view
        
        # 添加到堆叠窗口
        self.stacked_widget.addWidget(self.material_view)      # 0 - 素材生成
        self.stacked_widget.addWidget(self.finished_material_view) # 1 - 成品素材
        self.stacked_widget.addWidget(self.oral_broadcast_view) # 2 - 口播视频详情
        self.stacked_widget.addWidget(self.settings_view)       # 3 - 设置界面

        main_layout.addWidget(content_widget, 1)
        
        # 设置初始视图为素材生成
        self.stacked_widget.setCurrentIndex(0)
        self.current_sidebar_index = 0
    
    def create_sidebar(self):
        """创建左侧边栏"""
        sidebar = QWidget()
        sidebar.setFixedWidth(256)
        sidebar.setStyleSheet("""
            QWidget {
                background-color: #0f1219;
                border-right: 1px solid rgba(255, 255, 255, 0.1);
            }
        """)
        
        layout = QVBoxLayout(sidebar)
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
            ("素材生成", 0),
            ("成品素材", 1),
        ]
        
        self.sidebar_buttons = []
        for label, index in menu_items:
            btn = QPushButton(label)
            btn.setFixedHeight(48)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked, idx=index: self.on_sidebar_menu_clicked(idx))
            self.sidebar_buttons.append(btn)
            nav_layout.addWidget(btn)
        
        nav_widget = QWidget()
        nav_widget.setLayout(nav_layout)
        layout.addWidget(nav_widget, 1)
        
        # 更新按钮样式
        self.update_sidebar_button_styles()
        
        return sidebar
    
    def update_sidebar_button_styles(self):
        """更新侧边栏按钮样式"""
        for i, btn in enumerate(self.sidebar_buttons):
            if i == self.current_sidebar_index:
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
    
    def on_sidebar_menu_clicked(self, index):
        """侧边栏菜单点击事件"""
        self.current_sidebar_index = index
        self.update_sidebar_button_styles()
        
        if index == 0:
            # 素材生成
            self.stacked_widget.setCurrentIndex(0)
        elif index == 1:
            # 成品素材
            self.stacked_widget.setCurrentIndex(1)
    
    def on_oral_broadcast_clicked(self):
        """点击口播视频 - 在同一界面内切换"""
        self.stacked_widget.setCurrentIndex(2)  # 切换到口播视频详情
    
    def on_back_from_oral(self):
        """从口播视频返回 - 返回素材生成"""
        self.stacked_widget.setCurrentIndex(0)  # 返回素材生成
        self.current_sidebar_index = 0
        self.update_sidebar_button_styles()
    
    def on_settings_clicked(self):
        """点击设置按钮 - 切换到设置界面"""
        self.stacked_widget.setCurrentIndex(3)  # 切换到设置界面
    
    def on_back_from_settings(self):
        """从设置界面返回 - 返回素材生成"""
        self.stacked_widget.setCurrentIndex(0)  # 返回素材生成
        self.current_sidebar_index = 0
        self.update_sidebar_button_styles()
    
    def update_finished_material(self, video_path=None, script_text=""):
        """更新成品素材视图的内容"""
        if self.finished_material_view:
            if video_path:
                self.finished_material_view.set_video_path(video_path)
            if script_text:
                self.finished_material_view.set_script_text(script_text)

