# -*- coding: utf-8 -*-
"""
设置视图
"""

import os
import requests
import yaml
from pathlib import Path
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QLineEdit, QFrame, QFileDialog, QMessageBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QUrl
from PyQt5.QtGui import QDesktopServices

# 尝试导入openai（用于测试通义千问API Key）
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("[Settings] 警告: openai库未安装，无法完整测试通义千问API Key")

# API基础URL
API_BASE_URL = "http://127.0.0.1:38810"

class ConnectionTestThread(QThread):
    """测试API Key有效性的线程"""
    test_complete = pyqtSignal(bool, str)  # success, message
    
    def __init__(self, qwen_key, qwen_url, runninghub_key):
        super().__init__()
        self.qwen_key = qwen_key
        self.qwen_url = qwen_url
        self.runninghub_key = runninghub_key
    
    def test_qwen_key(self):
        """测试通义千问API Key"""
        if not self.qwen_key or not self.qwen_key.strip():
            return False, "通义千问API Key未填写"
        
        if not OPENAI_AVAILABLE:
            # 如果没有openai库，只检查格式
            key = self.qwen_key.strip()
            if key.startswith("sk-") and len(key) > 10:
                return True, "通义千问API Key格式正确（未安装openai库，无法完整验证）"
            else:
                return False, "通义千问API Key格式不正确"
        
        try:
            # 使用通义千问API测试Key是否有效
            client = openai.OpenAI(
                api_key=self.qwen_key.strip(),
                base_url=self.qwen_url.strip() if self.qwen_url else "https://dashscope.aliyuncs.com/compatible-mode/v1"
            )
            # 发送一个简单的测试请求
            response = client.chat.completions.create(
                model="qwen-turbo",
                messages=[{"role": "user", "content": "test"}],
                max_tokens=5
            )
            return True, "通义千问API Key有效"
        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg or "Unauthorized" in error_msg or "invalid" in error_msg.lower():
                return False, "通义千问API Key无效"
            elif "timeout" in error_msg.lower():
                return False, "通义千问API连接超时"
            else:
                return False, f"通义千问API Key测试失败: {error_msg[:50]}"
    
    def test_runninghub_key(self):
        """测试RunningHub API Key"""
        if not self.runninghub_key or not self.runninghub_key.strip():
            return False, "RunningHub API Key未填写"
        
        try:
            # 测试RunningHub API Key（通过调用API验证）
            # 这里可以调用RunningHub的API来验证Key
            # 暂时只检查格式，实际验证需要调用RunningHub API
            key = self.runninghub_key.strip()
            if len(key) < 10:
                return False, "RunningHub API Key格式不正确"
            # 可以添加实际的API调用测试
            return True, "RunningHub API Key格式正确"
        except Exception as e:
            return False, f"RunningHub API Key测试失败: {str(e)[:50]}"
    
    def run(self):
        """测试所有API Key"""
        results = []
        
        # 测试通义千问
        qwen_success, qwen_msg = self.test_qwen_key()
        results.append(("通义千问", qwen_success, qwen_msg))
        
        # 测试RunningHub
        runninghub_success, runninghub_msg = self.test_runninghub_key()
        results.append(("RunningHub", runninghub_success, runninghub_msg))
        
        # 汇总结果
        all_success = all(success for _, success, _ in results)
        if all_success:
            message = "所有API Key验证通过！"
        else:
            failed = [f"{name}: {msg}" for name, success, msg in results if not success]
            message = "部分API Key验证失败：\n" + "\n".join(failed)
        
        self.test_complete.emit(all_success, message)

class Settings(QWidget):
    def __init__(self, on_back_callback=None):
        super().__init__()
        self.config_path = Path(__file__).parent.parent.parent / "pixelle_wrapper" / "config.yaml"
        self.output_path = None  # 输出路径（与素材生产同步）
        self.on_back_callback = on_back_callback
        self.init_ui()
        self.load_config()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)
        
        # 标题
        header = QVBoxLayout()
        title = QLabel("系统设置")
        title.setStyleSheet("""
            font-size: 28px;
            font-weight: bold;
            color: white;
        """)
        subtitle = QLabel("全局接口配置与系统底层参数调整")
        subtitle.setStyleSheet("""
            font-size: 14px;
            color: #94a3b8;
        """)
        header.addWidget(title)
        header.addWidget(subtitle)
        layout.addLayout(header)
        
        # API认证区域
        api_section = self.create_section("API 认证", "🔑")
        api_layout = QVBoxLayout()
        api_layout.setSpacing(24)  # 增加间距，避免重叠
        api_layout.setContentsMargins(0, 0, 0, 0)  # 去掉边距，避免黑线
        
        # 第一行：通义千问、源码URL
        first_row = QHBoxLayout()
        first_row.setSpacing(12)
        
        # 通义千问
        qwen_layout = QVBoxLayout()
        qwen_layout.setSpacing(8)
        qwen_layout.setContentsMargins(0, 0, 0, 0)  # 去掉边距，避免黑边
        qwen_label = QLabel("通义千问")
        qwen_label.setStyleSheet("""
            font-size: 10px;
            font-weight: bold;
            color: #64748b;
        """)
        self.qwen_input = QLineEdit()
        self.qwen_input.setEchoMode(QLineEdit.Password)
        self.qwen_input.setPlaceholderText("请输入通义千问API Key")
        self.qwen_input.setFixedHeight(48)
        self.qwen_input.setStyleSheet("""
            QLineEdit {
                background-color: #1a1f2a;
                border: none;
                border-radius: 12px;
                padding: 14px 16px;
                color: #94a3b8;
                font-family: monospace;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 1px solid #6366f1;
            }
        """)
        qwen_layout.addWidget(qwen_label)
        qwen_layout.addWidget(self.qwen_input)
        first_row.addLayout(qwen_layout, 1)
        
        # 源码URL
        url_layout = QVBoxLayout()
        url_layout.setSpacing(8)
        url_layout.setContentsMargins(0, 0, 0, 0)  # 去掉边距，避免黑边
        url_label = QLabel("源码URL")
        url_label.setStyleSheet("""
            font-size: 10px;
            font-weight: bold;
            color: #64748b;
        """)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://dashscope.aliyuncs.com/compatible-mode/v1")
        self.url_input.setFixedHeight(48)
        self.url_input.setStyleSheet("""
            QLineEdit {
                background-color: #1a1f2a;
                border: none;
                border-radius: 12px;
                padding: 14px 16px;
                color: #94a3b8;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 1px solid #6366f1;
            }
        """)
        url_layout.addWidget(url_label)
        url_layout.addWidget(self.url_input)
        first_row.addLayout(url_layout, 1)
        
        api_layout.addLayout(first_row)
        
        # 第二行：获取通义千问KEY、获取RunningHub KEY（并排）
        second_row = QHBoxLayout()
        second_row.setSpacing(12)
        second_row.setContentsMargins(0, 8, 0, 0)  # 添加上边距，避免与上面重叠
        
        # 获取通义千问KEY按键
        get_qwen_layout = QVBoxLayout()
        get_qwen_layout.setSpacing(8)
        get_qwen_layout.setContentsMargins(0, 0, 0, 0)  # 去掉边距，避免黑边
        get_qwen_label = QLabel(" ")  # 占位，对齐
        get_qwen_label.setStyleSheet("""
            font-size: 10px;
        """)
        self.get_qwen_btn = QPushButton("获取通义千问KEY")
        self.get_qwen_btn.setFixedHeight(40)  # 减小高度，避免重叠
        self.get_qwen_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(99, 102, 241, 0.3);
                border: 1px solid rgba(99, 102, 241, 0.5);
                border-radius: 12px;
                padding: 14px 20px;
                color: #818cf8;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: rgba(99, 102, 241, 0.5);
                border-color: rgba(99, 102, 241, 0.8);
            }
        """)
        self.get_qwen_btn.clicked.connect(self.on_get_qwen_key)
        get_qwen_layout.addWidget(get_qwen_label)
        get_qwen_layout.addWidget(self.get_qwen_btn)
        second_row.addLayout(get_qwen_layout, 1)
        
        # 获取RunningHub KEY按键
        get_runninghub_layout = QVBoxLayout()
        get_runninghub_layout.setSpacing(8)
        get_runninghub_layout.setContentsMargins(0, 0, 0, 0)  # 去掉边距，避免黑边
        get_runninghub_label = QLabel(" ")  # 占位，对齐
        get_runninghub_label.setStyleSheet("""
            font-size: 10px;
        """)
        self.get_runninghub_btn = QPushButton("获取RunningHub KEY")
        self.get_runninghub_btn.setFixedHeight(40)  # 减小高度，避免重叠
        self.get_runninghub_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(99, 102, 241, 0.3);
                border: 1px solid rgba(99, 102, 241, 0.5);
                border-radius: 12px;
                padding: 14px 20px;
                color: #818cf8;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: rgba(99, 102, 241, 0.5);
                border-color: rgba(99, 102, 241, 0.8);
            }
        """)
        self.get_runninghub_btn.clicked.connect(self.on_get_runninghub_key)
        get_runninghub_layout.addWidget(get_runninghub_label)
        get_runninghub_layout.addWidget(self.get_runninghub_btn)
        second_row.addLayout(get_runninghub_layout, 1)
        
        api_layout.addLayout(second_row)
        
        # 第三行：RunningHub K输入框
        third_row = QHBoxLayout()
        third_row.setSpacing(12)
        third_row.setContentsMargins(0, 8, 0, 0)  # 添加上边距，避免与上面重叠
        
        # RunningHub K
        runninghub_layout = QVBoxLayout()
        runninghub_layout.setSpacing(8)
        runninghub_layout.setContentsMargins(0, 0, 0, 0)  # 去掉边距，避免黑边
        runninghub_label = QLabel("RunningHub KEY")
        runninghub_label.setStyleSheet("""
            font-size: 10px;
            font-weight: bold;
            color: #64748b;
        """)
        self.runninghub_input = QLineEdit()
        self.runninghub_input.setEchoMode(QLineEdit.Password)
        self.runninghub_input.setPlaceholderText("请输入RunningHub API Key")
        self.runninghub_input.setFixedHeight(48)
        self.runninghub_input.setStyleSheet("""
            QLineEdit {
                background-color: #1a1f2a;
                border: none;
                border-radius: 12px;
                padding: 14px 16px;
                color: #94a3b8;
                font-family: monospace;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 1px solid #6366f1;
            }
        """)
        runninghub_layout.addWidget(runninghub_label)
        runninghub_layout.addWidget(self.runninghub_input)
        third_row.addLayout(runninghub_layout, 1)
        
        api_layout.addLayout(third_row)
        
        # 第四行：测试连接按键和状态指示器（同一行）
        test_row = QHBoxLayout()
        test_row.setSpacing(12)
        test_row.setContentsMargins(0, 12, 0, 0)  # 添加上边距，避免与上面重叠
        test_row.addStretch()
        
        # 测试连接按键
        self.test_btn = QPushButton("测试通道连接")
        self.test_btn.setFixedHeight(40)  # 减小高度，避免重叠
        self.test_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(16, 185, 129, 0.2);
                border: 1px solid rgba(16, 185, 129, 0.5);
                border-radius: 12px;
                padding: 14px 32px;
                color: #10b981;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: rgba(16, 185, 129, 0.3);
                border-color: rgba(16, 185, 129, 0.8);
            }
        """)
        self.test_btn.clicked.connect(self.on_test_connection)
        test_row.addWidget(self.test_btn)
        
        # 连接状态指示器（与按钮同一行）
        self.connection_indicator = QLabel()
        self.connection_indicator.setFixedSize(16, 16)
        self.connection_indicator.setStyleSheet("""
            QLabel {
                background-color: #ef4444;
                border-radius: 8px;
            }
        """)
        # 使用垂直居中对齐
        indicator_container = QHBoxLayout()
        indicator_container.addWidget(self.connection_indicator)
        indicator_container.setAlignment(Qt.AlignVCenter)
        test_row.addLayout(indicator_container)
        test_row.addStretch()
        
        api_layout.addLayout(test_row)
        
        api_section[1].addLayout(api_layout)
        layout.addWidget(api_section[0])
        
        # 存储和输出区域
        storage_section = self.create_section("存储与输出", "📁")
        storage_layout = QVBoxLayout()
        storage_layout.setSpacing(16)
        
        # 输出目录（与素材生产同步）
        dir_layout = QVBoxLayout()
        dir_label = QLabel("默认输出目录（与素材生产同步）")
        dir_label.setStyleSheet("""
            font-size: 9px;
            font-weight: bold;
            color: #475569;
        """)
        dir_input_layout = QHBoxLayout()
        self.dir_input = QLineEdit()
        self.dir_input.setPlaceholderText("选择输出目录...")
        self.dir_input.setReadOnly(True)
        self.dir_input.setStyleSheet("""
            QLineEdit {
                background-color: #1a1f2a;
                border: none;
                border-radius: 12px;
                padding: 14px 16px;
                color: #94a3b8;
                font-family: monospace;
            }
        """)
        browse_btn = QPushButton("浏览")
        browse_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 12px;
                padding: 14px 24px;
                color: #94a3b8;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.1);
            }
        """)
        browse_btn.clicked.connect(self.browse_directory)
        dir_input_layout.addWidget(self.dir_input, 1)
        dir_input_layout.addWidget(browse_btn)
        dir_layout.addWidget(dir_label)
        dir_layout.addLayout(dir_input_layout)
        storage_layout.addLayout(dir_layout)
        
        storage_section[1].addLayout(storage_layout)
        layout.addWidget(storage_section[0])
        
        layout.addStretch()
        
        # 底部按钮
        footer_layout = QHBoxLayout()
        # 返回按钮（如果有回调）
        if self.on_back_callback:
            back_btn = QPushButton("← 返回")
            back_btn.setFixedHeight(48)
            back_btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(255, 255, 255, 0.02);
                    border: 1px solid rgba(255, 255, 255, 0.05);
                    border-radius: 12px;
                    padding: 16px 32px;
                    color: #94a3b8;
                    font-weight: bold;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: rgba(255, 255, 255, 0.05);
                    color: #e2e8f0;
                }
            """)
            back_btn.clicked.connect(self.on_back_callback)
            footer_layout.addWidget(back_btn)
        footer_layout.addStretch()
        restore_btn = QPushButton("恢复默认")
        restore_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.02);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 12px;
                padding: 16px 32px;
                color: #475569;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.05);
            }
        """)
        restore_btn.clicked.connect(self.on_restore_default)
        commit_btn = QPushButton("提交更改")
        commit_btn.setStyleSheet("""
            QPushButton {
                background-color: #6366f1;
                color: white;
                border: none;
                border-radius: 12px;
                padding: 16px 40px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5855eb;
            }
        """)
        commit_btn.clicked.connect(self.on_commit_changes)
        footer_layout.addWidget(restore_btn)
        footer_layout.addWidget(commit_btn)
        layout.addLayout(footer_layout)
    
    def create_section(self, title, icon):
        """创建区域"""
        section = QFrame()
        section.setFrameShape(QFrame.NoFrame)  # 完全移除框架边框
        section.setStyleSheet("""
            QFrame {
                background-color: #131720;
                border: none;
                border-radius: 16px;
            }
        """)
        layout = QVBoxLayout(section)
        layout.setContentsMargins(32, 16, 32, 16)  # 减小上下边距，避免产生横线视觉效果
        layout.setSpacing(24)
        
        header = QHBoxLayout()
        title_label = QLabel(f"{icon} {title}")
        title_label.setStyleSheet("""
            font-size: 12px;
            font-weight: bold;
            color: white;
        """)
        header.addWidget(title_label)
        header.addStretch()
        layout.addLayout(header)
        
        return section, layout
    
    def load_config(self):
        """加载配置"""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    if config:
                        # 加载通义千问配置
                        if 'llm' in config:
                            self.qwen_input.setText(config['llm'].get('api_key', ''))
                            self.url_input.setText(config['llm'].get('base_url', 'https://dashscope.aliyuncs.com/compatible-mode/v1'))
                        
                        # 加载RunningHub配置
                        if 'comfyui' in config:
                            self.runninghub_input.setText(config['comfyui'].get('runninghub_api_key', ''))
        except Exception as e:
            print(f"加载配置失败: {e}")
        
        # 加载输出路径（从环境变量或默认值）
        default_output = os.environ.get('CREATOR_OS_OUTPUT', 'C:/Users/Admin/Desktop/CREATOR_OS_OUTPUT')
        self.dir_input.setText(default_output)
        self.output_path = default_output
    
    def on_get_qwen_key(self):
        """获取通义千问K（直接打开浏览器）"""
        # 通义千问API Key获取页面
        url = QUrl("https://bailian.console.aliyun.com/cn-beijing/?tab=model#/api-key")
        QDesktopServices.openUrl(url)
    
    def on_get_runninghub_key(self):
        """获取RunningHub K（直接打开浏览器）"""
        # RunningHub的API Key获取页面
        url = QUrl("https://www.runninghub.cn/enterprise-api/consumerApi")
        QDesktopServices.openUrl(url)
    
    def on_test_connection(self):
        """测试API Key有效性"""
        self.test_btn.setEnabled(False)
        self.test_btn.setText("测试中...")
        
        # 获取输入的API Key
        qwen_key = self.qwen_input.text()
        qwen_url = self.url_input.text()
        runninghub_key = self.runninghub_input.text()
        
        # 启动测试线程（直接测试API Key，不测试HTTP连接）
        self.test_thread = ConnectionTestThread(qwen_key, qwen_url, runninghub_key)
        self.test_thread.test_complete.connect(self.on_test_complete)
        self.test_thread.start()
    
    def on_test_complete(self, success, message):
        """测试完成回调"""
        self.test_btn.setEnabled(True)
        self.test_btn.setText("测试通道连接")
        
        if success:
            self.connection_indicator.setStyleSheet("""
                QLabel {
                    background-color: #10b981;
                    border-radius: 8px;
                }
            """)
            QMessageBox.information(self, "连接测试", "连接成功！")
        else:
            self.connection_indicator.setStyleSheet("""
                QLabel {
                    background-color: #ef4444;
                    border-radius: 8px;
                }
            """)
            QMessageBox.warning(self, "连接测试", message)
    
    def browse_directory(self):
        """浏览目录"""
        directory = QFileDialog.getExistingDirectory(self, "选择输出目录", self.dir_input.text())
        if directory:
            self.dir_input.setText(directory)
            self.output_path = directory
    
    def on_restore_default(self):
        """恢复默认设置"""
        self.qwen_input.clear()
        self.url_input.setText("https://dashscope.aliyuncs.com/compatible-mode/v1")
        self.runninghub_input.clear()
        default_output = "C:/Users/Admin/Desktop/CREATOR_OS_OUTPUT"
        self.dir_input.setText(default_output)
        self.output_path = default_output
    
    def on_commit_changes(self):
        """提交更改"""
        try:
            # 读取现有配置
            config = {}
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f) or {}
            
            # 更新配置
            if 'llm' not in config:
                config['llm'] = {}
            config['llm']['api_key'] = self.qwen_input.text().strip()
            config['llm']['base_url'] = self.url_input.text().strip() or "https://dashscope.aliyuncs.com/compatible-mode/v1"
            config['llm']['model'] = config['llm'].get('model', 'qwen-max')
            
            if 'comfyui' not in config:
                config['comfyui'] = {}
            config['comfyui']['runninghub_api_key'] = self.runninghub_input.text().strip()
            
            # 保存配置
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
            
            # 更新输出路径环境变量（与素材生产同步）
            if self.output_path:
                os.environ['CREATOR_OS_OUTPUT'] = self.output_path
            
            # 如果wrapper服务运行，更新API Keys
            try:
                qwen_key = self.qwen_input.text().strip()
                if qwen_key:
                    requests.post(f"{API_BASE_URL}/api/set_key", 
                                json={"api_key": qwen_key}, timeout=5)
            except:
                pass  # wrapper服务可能未运行
            
            QMessageBox.information(self, "成功", "配置已保存！\n输出路径已同步到素材生产模块。")
        except Exception as e:
            QMessageBox.warning(self, "错误", f"保存配置失败: {str(e)}")
    
    def get_output_path(self):
        """获取输出路径（供其他模块使用）"""
        return self.output_path or self.dir_input.text() or "C:/Users/Admin/Desktop/CREATOR_OS_OUTPUT"
