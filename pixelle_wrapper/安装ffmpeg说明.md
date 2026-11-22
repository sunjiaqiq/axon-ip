# 安装 FFmpeg 说明

Whisper 需要 FFmpeg 来处理音频/视频文件。

## Windows 安装方法

### 方法1：使用 Chocolatey（推荐）
```powershell
choco install ffmpeg
```

### 方法2：使用 Scoop
```powershell
scoop install ffmpeg
```

### 方法3：手动安装（推荐用于项目内使用）
1. **访问FFMPEG官方网站：**
   - 官网：https://ffmpeg.org/download.html
   - Windows版本下载：https://www.gyan.dev/ffmpeg/builds/
   
2. **下载Windows版本：**
   - 选择 "ffmpeg-release-essentials.zip"（完整版，推荐）
   - 或 "ffmpeg-release-full.zip"（包含所有功能）
   
3. **解压到项目目录：**
   - 解压下载的zip文件
   - 将解压后的 `ffmpeg.exe`、`ffprobe.exe`、`ffplay.exe` 复制到 `env/ffmpeg/` 目录
   - 或者将整个 `bin` 文件夹的内容复制到 `env/ffmpeg/` 目录
   
4. **验证安装：**
   ```bash
   # 在项目根目录执行
   env\ffmpeg\ffmpeg.exe -version
   ```
   
   **注意：** 如果用于项目内使用，不需要添加到系统PATH，代码会自动查找 `env/ffmpeg/ffmpeg.exe`

### 验证安装
```powershell
ffmpeg -version
```

如果显示版本信息，说明安装成功。





