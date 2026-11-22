# Pixelle-Video FastAPI Wrapper

为 PyQt UI 提供稳定的 REST API 接口，封装 Pixelle-Video 的生成逻辑。

## 架构

```
PyQt UI
   ↓ HTTP
FastAPI Wrapper（本服务）
   ↓ Python 函数调用
Pixelle-Video 内部生成逻辑
```

## 项目结构

```
pixelle_wrapper/
├── main.py              # FastAPI 主程序（Wrapper 代码）
├── requirements.txt     # Python 依赖
├── start_wrapper.bat    # Windows 启动脚本
└── README.md           # 本文件
```

## 安装依赖

```bash
pip install -r requirements.txt
```

## 启动服务

### Windows
```bash
start_wrapper.bat
```

### 命令行
```bash
python main.py
```

服务将在 `http://127.0.0.1:38887` 启动。

## API 接口

### 1. 健康检查
```
GET /health
```
返回：`{"status": "ok"}`

### 2. 设置 API Key
```
POST /api/set_key
Content-Type: application/json

{
  "api_key": "your-api-key"
}
```

**行为**：
- 写入 `os.environ["PIXELLE_API_KEY"]`
- 存储到 `CURRENT_STATE["api_key"]`
- 不直接修改 `config.yaml`

### 3. 上传数字人形象
```
POST /api/avatar
Content-Type: multipart/form-data

file: <图片文件>
```

**行为**：
- 接收图片文件
- 保存到 `Y:/Video-main/data/avatars/`
- 更新 `CURRENT_STATE["avatar_path"]`

### 4. 设置口播文案
```
POST /api/text
Content-Type: application/json

{
  "text": "这是要口播的文案"
}
```

**行为**：
- 存储到 `CURRENT_STATE["text"]`

### 5. 生成视频
```
POST /api/generate
```

**返回**：
```json
{
  "success": true,
  "task_id": "uuid-string",
  "message": "任务已创建"
}
```

**行为**：
- 后台线程执行
- 真实调用 `Pixelle-Video.generate_video()`
- 返回 `task_id` 用于查询进度

### 6. 查询任务状态
```
GET /api/task/{task_id}
```

**返回**：
```json
{
  "status": "running | done | error",
  "progress": 0-100,
  "output": "video.mp4" 或 null,
  "error": "错误信息" 或 null
}
```

### 7. 下载生成视频
```
GET /api/download/{task_id}
```

**返回**：视频文件（`video/mp4`）

## 代码说明

### Wrapper 代码（新加的）
- `main.py` 中的所有 FastAPI 路由和状态管理
- `CURRENT_STATE` 字典：存储 avatar_path、text、api_key
- `TASKS` 字典：管理任务状态和进度
- 进度回调函数：将 Pixelle-Video 的进度事件转换为 Wrapper 的进度

### Pixelle-Video 原生逻辑（不修改）
- `PixelleVideoCore` 类：核心服务
- `generate_video()` 方法：真实的生成函数
- 所有 pipeline 和 service 代码

## 配置说明

### Pixelle-Video 路径
默认路径：`Y:/Video-main`

如需修改，编辑 `main.py` 中的：
```python
PIXELLE_VIDEO_PATH = Path("Y:/Video-main")
```

### 服务端口
默认端口：`38887`

如需修改，编辑 `main.py` 中的：
```python
uvicorn.run(
    "main:app",
    host="127.0.0.1",
    port=38887,  # 修改这里
    log_level="info"
)
```

## 使用流程

1. **启动 Wrapper 服务**
   ```bash
   python main.py
   ```

2. **PyQt UI 调用流程**：
   - 调用 `GET /health` 检查服务
   - 调用 `POST /api/set_key` 设置 API Key
   - 调用 `POST /api/avatar` 上传人物照片
   - 调用 `POST /api/text` 设置文案
   - 调用 `POST /api/generate` 开始生成
   - 轮询 `GET /api/task/{task_id}` 获取进度
   - 调用 `GET /api/download/{task_id}` 下载视频

## 注意事项

1. **Pixelle-Video 路径**：确保 `Y:/Video-main` 路径正确，或修改代码中的路径
2. **API Key**：通过 `/api/set_key` 设置，不直接修改配置文件
3. **进度跟踪**：Wrapper 内部维护任务状态，通过进度回调实时更新
4. **错误处理**：所有错误都会记录到任务状态中，可通过 `/api/task/{task_id}` 查询

## 故障排除

### 问题：无法导入 Pixelle-Video
- **检查**：`Y:/Video-main` 路径是否存在
- **解决**：修改 `main.py` 中的 `PIXELLE_VIDEO_PATH`

### 问题：生成失败
- **检查**：API Key 是否已设置
- **检查**：文案是否已设置
- **检查**：查看控制台错误信息

### 问题：进度不更新
- **检查**：任务状态是否为 "running"
- **检查**：Pixelle-Video 是否正常生成
- **解决**：查看控制台日志









