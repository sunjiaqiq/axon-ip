# Axon IP · 全自动智能口播与获客系统

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10+-green.svg)](https://www.python.org/)
[![React](https://img.shields.io/badge/React-19-61dafb.svg)](https://react.dev/)

> 开源版：**内容生产（解析 → 文案 → 口播 → 成片）+ 多平台发布 + 截流找客户**。  
> 不含微信私域 RPA（`Axon-siyu`）与服务器账号密码；密钥请用环境变量自行配置。

---

## 功能一览

| 模块 | 说明 |
|------|------|
| **链接解析** | 抖音 / 快手 / 小红书等链接解析，提取口播文案 |
| **文案生产** | AI 二创、人设配置、爆款结构模板 |
| **合规检测** | 敏感词 / 私域话术等规则检测与改写辅助 |
| **数字人口播** | 形象 + 音频 → 口播视频（RunningHub / Pixelle 工作流） |
| **成品素材** | 字幕时间轴、封面标题描述、再次合成 |
| **分发发布** | 抖音 / 快手 / 小红书 / 微信视频号自动化发布 |
| **截流找客户** | 关键词刷同领域内容、意向评论识别、互动与引导 |
| **自动回复** | 评论区 / 私信侧辅助回复（与截流互斥调度，避免抢同一浏览器配置） |
| **自动化编排** | 「自动化模块」一键串联：解析 → 文案 → 合规 → 口播 → 发布 |

> 界面侧栏「分身直播」仅为外部工具下载入口，不包含在本仓库运行时依赖中。

---

## 架构概览

```
┌──────────────────────────────────────────────┐
│  React + Vite 前端（views / components）      │
│  自动化 · 文案 · 合规 · 口播 · 成品 · 分发 · 设置 │
└─────────────────────┬────────────────────────┘
                      │ HTTP / REST
┌─────────────────────▼────────────────────────┐
│  FastAPI：pixelle_wrapper                    │
│  任务编排 · 解析 · 截流 · 发布 · 账号对接(可选)   │
└───────┬───────────────┬───────────────┬──────┘
        │               │               │
   Video-main      Selenium/Chrome    publish/
   (数字人引擎)     (平台自动化)      (视频号)
```

更细的目录说明见 [`系统架构文档.md`](./系统架构文档.md)。

---

## 环境要求

- Windows 10/11（发布与截流依赖本机 Chrome / 可选 PC 微信）
- Python **3.10+**
- Node.js **18+**（前端开发 / 构建）
- 已安装 **Google Chrome**
- （口播云端）[RunningHub](https://www.runninghub.cn/) API Key  
- （文案 / 自动化）兼容 OpenAI 接口的大模型 Key（如通义 DashScope、硅基流动等）

---

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/sunjiaqiq/axon-ip.git
cd axon-ip
```

### 2. 配置密钥（不要提交真实 Key）

```bash
copy .env.example .env
# 编辑 .env，以及 pixelle_wrapper/config.yaml 中的空字段
```

必填建议：

- `pixelle_wrapper/config.yaml` → `llm.api_key` 或环境变量 `PIXELLE_API_KEY`
- `comfyui.runninghub_api_key` 或 `RUNNINGHUB_API_KEY`（口播生成）
- 可选：`siliconflow.api_key`（部分浏览器自动化能力）

### 3. 安装依赖

```bash
# 前端
npm install

# 后端（建议使用虚拟环境）
pip install -r requirements.txt
pip install -r pixelle_wrapper/requirements.txt
pip install -r pixelle_wrapper/requirements_runtime.txt`n# 视频下载（勿再 vendoring yt-dlp 源码）`npip install -U yt-dlp
```

ChromeDriver：仓库 `env/chromedriver` 提供参考驱动，**主版本需与本机 Chrome 一致**，否则请从 [Chrome for Testing](https://googlechromelabs.github.io/chrome-for-testing/) 下载替换。

### 4. 启动

```bash
# 终端 1：后端
python -m uvicorn pixelle_wrapper.main:app --host 127.0.0.1 --port 8000
# 或以项目内启动脚本 / launcher.py

# 终端 2：前端开发
npm run dev
```

生产前端可先 `npm run build`，使用已生成的 `web/` 静态资源由后端托管（视你的启动方式而定）。

开源默认**不启用**启动账号门禁。若需门禁，构建前设置：

```bash
set VITE_ACCOUNT_API_BASE=http://your-account-server
npm run build
```

---

## 目录结构（开源包）

```
axon-ip/
├── App.tsx / views / components   # React 界面
├── pixelle_wrapper/               # FastAPI 后端与业务脚本
│   ├── main.py
│   ├── config.yaml                # 模板（无真实密钥）
│   ├── ai_pipeline/               # 解析、合规、下载等
│   ├── test_intercept_selenium.py # 截流找客户
│   └── hf_auto_reply.py           # 自动回复相关
├── Video-main/                    # 数字人 / Pixelle 核心
├── publish/                       # 微信视频号发布（pyweixin）
├── douyin-mcp-server-main/        # 抖音解析
├── TikTokDownloader-master/       # Cookie API 兜底下载
├── whisper-main/                  # Whisper 字幕（亦可 pip 安装 openai-whisper）
├── web/                           # 前端构建产物
├── env/                           # 驱动与部署说明（不含完整 Chrome）
├── .env.example
└── docs/                          # 补充文档
```

**未纳入本仓库：** 微信私域全自动运营（见 [Axon-siyu](https://github.com/sunjiaqiq/Axon-siyu)）、客户定制「霍客版」、本机登录态 / Cookie / 服务器账号体系密钥。

---

## 配置说明

| 配置项 | 位置 | 用途 |
|--------|------|------|
| LLM API Key | `config.yaml` → `llm` 或 `PIXELLE_API_KEY` | 文案、改写、部分智能能力 |
| RunningHub Key | `config.yaml` → `comfyui.runninghub_api_key` | 口播视频云端生成 |
| 硅基流动 Key | `config.yaml` → `siliconflow` | 自动化辅助模型 |
| 人设 / 微信号 | 客户端「文案创作 → 配置人设」 | 截流话术；**勿把真实微信号写进仓库** |
| 浏览器 Profile | `config.yaml` → `browser.profile_directory` | 与发布 / 登录共用 |

---

## 使用提示

1. 首次在「系统设置」用程序专用 Chrome 登录抖音 / 快手 / 小红书。  
2. 视频号发布需本机已登录 **PC 微信**。  
3. 截流与自动回复会占用同一浏览器用户数据目录，系统内有互斥调度，避免并行抢配置。  
4. 平台自动化受对方页面改版影响，若选择器失效需自行适配。

---

## 安全与合规

- 仓库内 **不含** 可用的服务器密码与生产 API Key；发现历史泄露请立刻在云平台轮换密钥。  
- 请遵守各平台用户协议与当地法律法规，勿用于骚扰、欺诈或违规营销。  
- 开源码仅供学习与二次开发；商业使用请自行承担合规责任。

---

## 相关仓库

- [Axon-siyu](https://github.com/sunjiaqiq/Axon-siyu) — 微信私域运营（本开源包不包含）
- [pywechat](https://github.com/sunjiaqiq/pywechat) — 微信 RPA 相关

---

## License

[MIT](./LICENSE) © sunjiaqiq

演示与产品介绍可参考仓库历史说明或作者飞书文档；本 README 以**可运行源码与工程说明**为准。

