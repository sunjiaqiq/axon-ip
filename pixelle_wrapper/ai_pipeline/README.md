# AI短视频自动生产系统

## 模块说明

### 1. crawler.py - 视频爬虫
- 使用浏览器自动化（Playwright）搜索中国抖音爆款视频
- 筛选条件：播放量 > 10万，点赞数 > 5000
- 返回前10条符合条件的视频

### 2. video_downloader.py - 视频下载
- 使用 yt-dlp 下载视频（支持抖音、快手等平台）
- 统一格式为 mp4
- 保存到 materials/ 目录

### 3. script_extractor.py - 文案提取
- 从视频描述中提取结构化内容
- 提取：hook（钩子）、problem（问题）、solution（解决方案）、cta（行动号召）

### 4. script_rewriter.py - 文案改写
- 使用 GPT API 改写文案
- 避免重复，更加口语化
- 适合50-80秒口播

### 5. subtitle_generator.py - 字幕生成
- 使用 Whisper 从音频生成字幕
- 输出 SRT 格式字幕文件

### 6. video_editor.py - 视频编辑
- 使用 MoviePy 插入素材
- 时间轴：0-3秒主播，3-5秒素材，5-8秒主播，8-10秒素材，循环插入

### 7. original_filter.py - 原创处理
- 避免视频hash重复
- 随机执行：速度1.02x、裁剪3%、镜像30%概率
- 实现原创检测规避

### 8. publisher.py - 发布模块
- 使用 Playwright 自动上传视频
- 支持抖音、快手、小红书等平台

### 9. pipeline.py - 完整流程
- 整合所有模块
- 实现从关键词到最终视频的完整流程

## API接口

### POST /api/auto_generate

请求体：
```json
{
  "keyword": "宠物医院",
  "avatar_path": "可选",
  "product_path": "可选"
}
```

响应：
```json
{
  "success": true,
  "video_path": "最终视频路径",
  "subtitle_path": "字幕文件路径",
  "script": "生成的文案",
  "message": "视频生成成功"
}
```

## 依赖安装

```bash
pip install -r requirements.txt
```

主要依赖：
- yt-dlp
- openai-whisper
- moviepy
- openai
- playwright
- numpy

## 使用说明

1. 确保已安装所有依赖
2. 配置 API 密钥（OpenAI 或 Gemini）
3. 启动 FastAPI 服务
4. 调用 `/api/auto_generate` 接口

## 注意事项

- 原创处理是关键功能，确保视频hash不同
- 文案改写需要API密钥
- 视频下载需要网络连接
- 发布功能需要登录cookies

