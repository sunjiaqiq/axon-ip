# douyin-mcp-server 使用说明

## 配置

API Key 已配置在 `config.env` 文件中：
```
API_KEY=${SILICONFLOW_API_KEY}
```

## 使用方法

### 方法1：使用测试脚本（推荐）

```bash
cd douyin-mcp-server-main
py -3 test_extract_with_mcp.py
```

### 方法2：使用命令行工具

```bash
cd douyin-mcp-server-main
set API_KEY=${SILICONFLOW_API_KEY}
py -3 douyin-video/scripts/douyin_downloader.py -l "抖音分享链接" -a extract -o ./output
```

## 输出

文案会保存到 `output/视频ID/transcript.md` 文件中，包含：
- 视频标题
- 视频ID
- 提取时间
- 下载链接
- **完整的文案内容**（使用硅基流动 SenseVoice API 识别，质量高）

## 注意事项

1. 需要 FFmpeg（已复制到 `env/ffmpeg/`）
2. 需要网络连接（下载视频和调用 API）
3. API Key 已配置，可直接使用







