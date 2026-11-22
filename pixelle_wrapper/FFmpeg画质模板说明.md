# FFmpeg 画质模板说明

## 📋 当前代码中使用的参数

### 1. 视频编辑模块 (`video_editor.py`)
```python
codec='libx264'
audio_codec='aac'
fps=30
preset='medium'
bitrate='8000k'
```

### 2. 原创处理模块 (`original_filter.py`)
```python
codec='libx264'
audio_codec='aac'
fps=30
preset='medium'
bitrate='8000k'
```

### 3. 音频提取模块 (`audio_extractor.py`)
```python
codec='mp3'
bitrate='192k'
```

---

## 🎬 FFmpeg/MoviePy 支持的画质预设 (Preset)

### H.264 编码预设 (libx264 preset)
这些预设控制编码速度和压缩效率的平衡：

| 预设 | 编码速度 | 文件大小 | 画质 | 适用场景 |
|------|---------|---------|------|---------|
| `ultrafast` | ⚡⚡⚡⚡⚡ 最快 | 最大 | 较低 | 快速预览、测试 |
| `superfast` | ⚡⚡⚡⚡ 很快 | 较大 | 较低 | 快速转码 |
| `veryfast` | ⚡⚡⚡ 很快 | 较大 | 中等 | 实时转码 |
| `faster` | ⚡⚡ 较快 | 中等 | 中等 | 批量处理 |
| `fast` | ⚡ 快 | 中等 | 中等 | 日常使用 |
| `medium` | ⚖️ 平衡 | 中等 | 良好 | **当前使用** |
| `slow` | 🐢 慢 | 较小 | 很好 | 高质量输出 |
| `slower` | 🐢🐢 很慢 | 小 | 优秀 | 专业制作 |
| `veryslow` | 🐢🐢🐢 极慢 | 最小 | 最佳 | 最终成品 |

---

## 📊 常用比特率 (Bitrate) 模板

### 视频比特率 (Video Bitrate)
| 分辨率 | 推荐比特率 | 说明 |
|--------|-----------|------|
| 480p (SD) | `1000k` - `2000k` | 标清视频 |
| 720p (HD) | `2500k` - `5000k` | 高清视频 |
| 1080p (Full HD) | `5000k` - `8000k` | **当前使用 8000k** |
| 1440p (2K) | `10000k` - `15000k` | 2K视频 |
| 2160p (4K) | `20000k` - `40000k` | 4K视频 |

### 音频比特率 (Audio Bitrate)
| 质量 | 比特率 | 说明 |
|------|--------|------|
| 低质量 | `64k` - `96k` | 语音通话 |
| 中等质量 | `128k` - `192k` | **当前使用 192k** |
| 高质量 | `256k` - `320k` | 音乐、专业视频 |

---

## 🎯 推荐的画质模板配置

### 模板1: 快速预览 (Fast Preview)
```python
{
    'codec': 'libx264',
    'audio_codec': 'aac',
    'fps': 30,
    'preset': 'ultrafast',
    'bitrate': '2000k',
    'audio_bitrate': '128k'
}
```
**用途**: 快速测试、预览效果

### 模板2: 标准质量 (Standard Quality) - **当前使用**
```python
{
    'codec': 'libx264',
    'audio_codec': 'aac',
    'fps': 30,
    'preset': 'medium',
    'bitrate': '8000k',
    'audio_bitrate': '192k'
}
```
**用途**: 日常视频处理、抖音发布

### 模板3: 高质量 (High Quality)
```python
{
    'codec': 'libx264',
    'audio_codec': 'aac',
    'fps': 30,
    'preset': 'slow',
    'bitrate': '12000k',
    'audio_bitrate': '256k'
}
```
**用途**: 高质量输出、专业制作

### 模板4: 最佳质量 (Best Quality)
```python
{
    'codec': 'libx264',
    'audio_codec': 'aac',
    'fps': 30,
    'preset': 'veryslow',
    'bitrate': '15000k',
    'audio_bitrate': '320k'
}
```
**用途**: 最终成品、存档

### 模板5: 移动端优化 (Mobile Optimized)
```python
{
    'codec': 'libx264',
    'audio_codec': 'aac',
    'fps': 30,
    'preset': 'fast',
    'bitrate': '4000k',
    'audio_bitrate': '128k'
}
```
**用途**: 移动端播放、节省流量

### 模板6: 低带宽 (Low Bandwidth)
```python
{
    'codec': 'libx264',
    'audio_codec': 'aac',
    'fps': 24,
    'preset': 'veryfast',
    'bitrate': '1500k',
    'audio_bitrate': '96k'
}
```
**用途**: 网络传输、低带宽环境

---

## 🔧 其他编码参数

### CRF (Constant Rate Factor) - 质量模式
使用 CRF 可以替代比特率，自动调整质量：
- `crf=18`: 视觉无损（文件较大）
- `crf=23`: 高质量（默认推荐）
- `crf=28`: 中等质量
- `crf=32`: 低质量（文件较小）

### 编码配置文件 (Profile)
- `baseline`: 兼容性最好，适合旧设备
- `main`: 平衡兼容性和质量
- `high`: 最佳质量，需要较新设备

### 编码级别 (Level)
- `3.0`, `3.1`, `3.2`: 标清
- `4.0`, `4.1`, `4.2`: 高清
- `5.0`, `5.1`, `5.2`: 2K/4K

---

## 📝 使用示例

### MoviePy 使用示例
```python
clip.write_videofile(
    output_path,
    codec='libx264',
    audio_codec='aac',
    fps=30,
    preset='medium',      # 编码预设
    bitrate='8000k',     # 视频比特率
    audio_bitrate='192k' # 音频比特率
)
```

### 直接使用 FFmpeg 命令示例
```bash
ffmpeg -i input.mp4 \
  -c:v libx264 \
  -preset medium \
  -b:v 8000k \
  -c:a aac \
  -b:a 192k \
  -r 30 \
  output.mp4
```

---

## ⚠️ 注意事项

1. **编码速度 vs 文件大小**: 预设越慢，文件越小，但编码时间越长
2. **比特率 vs 分辨率**: 分辨率越高，需要的比特率越高
3. **平台限制**: 抖音等平台可能有比特率上限，建议不超过 10Mbps
4. **文件大小**: 高比特率会产生大文件，注意存储空间

---

## 🔄 建议

目前代码中所有视频处理都使用相同的参数（`preset='medium'`, `bitrate='8000k'`）。

**建议创建画质模板配置文件**，允许根据不同场景选择不同的画质模板。




