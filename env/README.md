# 环境配置说明

## 快速安装

### Windows
```bash
cd env
install.bat
```

### Linux/Mac
```bash
cd env
chmod +x install.sh
./install.sh
```

## 手动安装

### 1. 安装Python依赖
```bash
pip install -r requirements.txt
```

### 2. 安装Playwright浏览器驱动
```bash
playwright install chromium
```

### 3. 安装Whisper模型（首次使用会自动下载）
```bash
python -c "import whisper; whisper.load_model('base')"
```

## 依赖说明

### 核心依赖
- **fastapi**: Web框架
- **yt-dlp**: 视频下载工具
- **openai-whisper**: 语音识别和字幕生成
- **moviepy**: 视频编辑
- **playwright**: 浏览器自动化
- **numpy**: 数值计算

### 可选依赖
- **tiktokapi**: TikTok视频爬取（如果项目中有TikTok-Api-main目录）

## 环境变量配置

在系统环境变量或 `.env` 文件中设置：

```bash
# AI API配置（已内置默认值）
AI_API_URL=https://new.12ai.org/v1/chat/completions
AI_API_KEY=

# Pixelle-Video路径（可选）
PIXELLE_VIDEO_ROOT=/path/to/Video-main
```

## 注意事项

1. **Python版本**: 需要 Python 3.10 或更高版本
2. **FFmpeg**: MoviePy需要FFmpeg，Windows用户需要单独安装
3. **磁盘空间**: Whisper模型需要约500MB空间
4. **网络**: 首次运行需要下载模型和浏览器驱动

## 验证安装

运行以下命令验证所有依赖是否正确安装：

```bash
python -c "import fastapi, yt_dlp, whisper, moviepy, playwright; print('✓ 所有依赖安装成功！')"
```

## 常见问题

### 1. MoviePy安装失败
- Windows: 需要安装FFmpeg
- 下载地址: https://ffmpeg.org/download.html

### 2. Whisper模型下载慢
- 可以手动下载模型文件
- 或使用国内镜像源

### 3. Playwright浏览器安装失败
- 检查网络连接
- 使用代理：`playwright install chromium --with-deps`







