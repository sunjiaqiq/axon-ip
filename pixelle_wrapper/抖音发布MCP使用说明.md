# 抖音发布 MCP Server 使用说明

## 简介

这是一个基于 `fastmcp` 实现的抖音视频发布 MCP Server，可以在 MCP Client（如 Claude Desktop）中调用，实现自动发布视频到抖音。

## 功能特点

- ✅ 使用指定的 Chrome Profile 3（可配置）
- ✅ 隐藏自动化标识（无"正受到自动测试软件控制"提示）
- ✅ 完整的发布流程：上传视频 → 选择封面 → 填写标题 → 填写描述 → 发布
- ✅ 自动提取封面（如果未提供）
- ✅ 持久化浏览器状态（保持登录）

## 安装

### 1. 安装依赖

```bash
pip install fastmcp playwright
playwright install
```

### 2. 配置浏览器

在 `config.yaml` 中配置浏览器路径和 Profile：

```yaml
browser:
  chrome_path: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
  profile_directory: "Profile 3"
```

## MCP Client 配置

### Claude Desktop 配置示例

编辑 Claude Desktop 的配置文件（通常在 `%APPDATA%\Claude\claude_desktop_config.json`）：

```json
{
  "mcpServers": {
    "douyin_publisher": {
      "command": "C:\\Program Files\\Python311\\python.exe",
      "args": [
        "F:\\shuziren\\pixelle_wrapper\\douyin_publish_mcp.py",
        "--stdio"
      ]
    }
  }
}
```

**注意**：
- 使用 Python 解释器的完整绝对路径
- 使用 `douyin_publish_mcp.py` 的完整绝对路径
- Windows 路径中的反斜杠在 JSON 中需要转义（使用 `\\`）

## 可用工具

### 1. publish_video

发布视频到抖音

**参数**：
- `video_path` (str): 视频文件路径（必需）
- `title` (str): 视频标题（必需）
- `description` (str): 视频描述（必需）
- `cover_path` (str, 可选): 封面图片路径（如果不提供，会从视频自动提取）

**返回**：
- 发布结果字符串

**使用示例**（在 Claude Desktop 中）：
```
帮我发布视频到抖音：
- 视频路径: F:\shuziren\pixelle_wrapper\output\xxx\final.mp4
- 标题: 测试视频
- 描述: 这是一个测试视频
```

### 2. check_browser_status

检查浏览器状态

**参数**：无

**返回**：
- 浏览器状态信息

**使用示例**：
```
检查浏览器状态
```

## 发布流程

MCP Server 会自动执行以下流程：

1. **上传视频** - 自动上传视频文件
2. **选择封面**（按指定顺序）：
   - 点击"选择封面"按钮
   - 点击"标题"按钮
   - 点击 canvas 中间区域
   - 上传封面文件
   - 点击"确定"按钮
   - 点击"完成"按钮
3. **填写标题** - 自动填写视频标题
4. **填写描述** - 自动填写视频描述
5. **点击发布** - 自动点击发布按钮
6. **等待发布成功** - 检测 URL 变化或成功提示

## 测试

运行测试脚本：

```bash
python test_douyin_mcp.py
```

## 注意事项

1. **首次使用**：需要手动在浏览器中登录抖音账号
2. **浏览器配置**：确保使用正确的 Chrome Profile（Profile 3）
3. **文件路径**：使用绝对路径，避免相对路径问题
4. **发布频率**：建议控制发布频率，避免账号风险

## 故障排除

### 浏览器启动失败

- 检查 Chrome 路径是否正确
- 检查 Profile 3 是否存在
- 确保没有其他 Chrome 实例占用该 Profile

### 找不到元素

- 抖音页面结构可能已更新，需要更新选择器
- 检查页面是否完全加载

### 发布失败

- 检查是否已登录
- 检查视频文件是否存在
- 检查网络连接





