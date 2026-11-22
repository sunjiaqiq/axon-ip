# FFmpeg 花字模板大全

使用文字："**测试文字**" 作为示例

---

## 📝 基础 drawtext 语法

```bash
drawtext=text='测试文字':参数1=值1:参数2=值2:...
```

---

## 🎨 模板1: 基础白色文字（左上角）

**效果**: 白色文字，左上角显示

```bash
-vf "drawtext=text='测试文字':fontcolor=white:fontsize=48:x=10:y=10"
```

**参数说明**:
- `fontcolor=white` - 字体颜色：白色
- `fontsize=48` - 字体大小：48像素
- `x=10:y=10` - 位置：左上角（距离左边10，距离顶部10）

---

## 🎨 模板2: 红色粗体文字（居中）

**效果**: 红色粗体文字，屏幕中央

```bash
-vf "drawtext=text='测试文字':fontcolor=red:fontsize=60:x=(w-text_w)/2:y=(h-text_h)/2:fontfile=arial.ttf:fontsize=60"
```

**参数说明**:
- `fontcolor=red` - 字体颜色：红色
- `x=(w-text_w)/2` - 水平居中
- `y=(h-text_h)/2` - 垂直居中
- `fontsize=60` - 字体大小：60像素

---

## 🎨 模板3: 黄色描边文字（底部居中）

**效果**: 黄色文字，黑色描边，底部居中

```bash
-vf "drawtext=text='测试文字':fontcolor=yellow:fontsize=50:x=(w-text_w)/2:y=h-th-20:borderw=3:bordercolor=black"
```

**参数说明**:
- `fontcolor=yellow` - 字体颜色：黄色
- `borderw=3` - 描边宽度：3像素
- `bordercolor=black` - 描边颜色：黑色
- `y=h-th-20` - 位置：底部（距离底部20像素）

---

## 🎨 模板4: 渐变彩色文字（顶部）

**效果**: 彩色文字，顶部显示

```bash
-vf "drawtext=text='测试文字':fontcolor=0xFF00FF:fontsize=55:x=10:y=30"
```

**颜色代码**:
- `0xFF0000` - 红色
- `0x00FF00` - 绿色
- `0x0000FF` - 蓝色
- `0xFFFF00` - 黄色
- `0xFF00FF` - 紫色（洋红）
- `0x00FFFF` - 青色

---

## 🎨 模板5: 带阴影的文字（右下角）

**效果**: 白色文字，黑色阴影

```bash
-vf "drawtext=text='测试文字':fontcolor=white:fontsize=48:x=w-tw-20:y=h-th-20:shadowx=4:shadowy=4:shadowcolor=black@0.8"
```

**参数说明**:
- `shadowx=4` - 阴影X偏移：4像素
- `shadowy=4` - 阴影Y偏移：4像素
- `shadowcolor=black@0.8` - 阴影颜色：黑色，透明度0.8

---

## 🎨 模板6: 半透明背景文字（居中）

**效果**: 白色文字，半透明黑色背景

```bash
-vf "drawtext=text='测试文字':fontcolor=white:fontsize=50:x=(w-text_w)/2:y=(h-text_h)/2:box=1:boxcolor=black@0.5:boxborderw=5"
```

**参数说明**:
- `box=1` - 启用背景框
- `boxcolor=black@0.5` - 背景颜色：黑色，透明度0.5
- `boxborderw=5` - 背景框内边距：5像素

---

## 🎨 模板7: 抖音风格 - 粉色文字（底部）

**效果**: 粉色文字，白色描边，底部显示

```bash
-vf "drawtext=text='测试文字':fontcolor=0xFF1493:fontsize=52:x=(w-text_w)/2:y=h-th-50:borderw=4:bordercolor=white"
```

**参数说明**:
- `fontcolor=0xFF1493` - 字体颜色：深粉色（抖音色）
- `bordercolor=white` - 描边颜色：白色

---

## 🎨 模板8: 霓虹灯效果（闪烁文字）

**效果**: 彩色文字，闪烁效果

```bash
-vf "drawtext=text='测试文字':fontcolor=0x00FFFF:fontsize=60:x=(w-text_w)/2:y=(h-text_h)/2:enable='between(t,0,10)':alpha='if(lt(mod(t,1),0.5),1,0.7)'"
```

**参数说明**:
- `enable='between(t,0,10)'` - 显示时间：0-10秒
- `alpha='if(lt(mod(t,1),0.5),1,0.7)'` - 透明度动画：闪烁效果

---

## 🎨 模板9: 滚动文字（从右到左）

**效果**: 文字从右向左滚动

```bash
-vf "drawtext=text='测试文字':fontcolor=white:fontsize=48:x='w-mod(t*50,w+tw)':y=50"
```

**参数说明**:
- `x='w-mod(t*50,w+tw)'` - X位置动画：从右向左滚动
- `t*50` - 滚动速度：每秒50像素

---

## 🎨 模板10: 打字机效果（逐字显示）

**效果**: 文字逐字显示

```bash
-vf "drawtext=text='测试文字':fontcolor=white:fontsize=50:x=10:y=100:enable='between(t,0,2)':text='%{eif\:substr(txt,0,floor(t*2))\:d}'"
```

---

## 🎨 模板11: 彩虹渐变文字

**效果**: 彩虹色文字

```bash
-vf "drawtext=text='测试文字':fontcolor=0xFF0000:fontsize=55:x=(w-text_w)/2:y=100:fontcolor=0xFF7F00:fontsize=55:x=(w-text_w)/2:y=100"
```

**注意**: 需要多个drawtext叠加实现渐变效果

---

## 🎨 模板12: 立体3D文字

**效果**: 3D立体效果文字

```bash
-vf "drawtext=text='测试文字':fontcolor=white:fontsize=60:x=(w-text_w)/2+2:y=(h-text_h)/2+2:shadowx=2:shadowy=2:shadowcolor=black,drawtext=text='测试文字':fontcolor=white:fontsize=60:x=(w-text_w)/2:y=(h-text_h)/2"
```

**说明**: 使用两层文字叠加，下层偏移形成3D效果

---

## 🎨 模板13: 抖音热门 - 金色文字

**效果**: 金色文字，黑色描边

```bash
-vf "drawtext=text='测试文字':fontcolor=0xFFD700:fontsize=56:x=(w-text_w)/2:y=(h-text_h)/2:borderw=5:bordercolor=black"
```

**参数说明**:
- `fontcolor=0xFFD700` - 字体颜色：金色

---

## 🎨 模板14: 简约风格 - 白色细线

**效果**: 白色细线文字，无描边

```bash
-vf "drawtext=text='测试文字':fontcolor=white:fontsize=40:x=(w-text_w)/2:y=80"
```

---

## 🎨 模板15: 醒目警告 - 红底白字

**效果**: 红色背景，白色文字

```bash
-vf "drawtext=text='测试文字':fontcolor=white:fontsize=50:x=(w-text_w)/2:y=(h-text_h)/2:box=1:boxcolor=red:boxborderw=10"
```

---

## 🎨 模板16: 优雅风格 - 灰色文字

**效果**: 灰色文字，顶部显示

```bash
-vf "drawtext=text='测试文字':fontcolor=0x808080:fontsize=45:x=(w-text_w)/2:y=30"
```

---

## 🎨 模板17: 活力风格 - 橙色文字

**效果**: 橙色文字，白色描边

```bash
-vf "drawtext=text='测试文字':fontcolor=0xFF6600:fontsize=54:x=(w-text_w)/2:y=(h-text_h)/2:borderw=3:bordercolor=white"
```

---

## 🎨 模板18: 科技风格 - 青色文字

**效果**: 青色文字，发光效果

```bash
-vf "drawtext=text='测试文字':fontcolor=0x00FFFF:fontsize=58:x=(w-text_w)/2:y=(h-text_h)/2:shadowx=0:shadowy=0:shadowcolor=0x00FFFF@0.8"
```

---

## 🎨 模板19: 可爱风格 - 粉色文字

**效果**: 粉色文字，圆润字体

```bash
-vf "drawtext=text='测试文字':fontcolor=0xFFB6C1:fontsize=52:x=(w-text_w)/2:y=(h-text_h)/2:borderw=2:bordercolor=white"
```

---

## 🎨 模板20: 商务风格 - 深蓝文字

**效果**: 深蓝色文字，专业风格

```bash
-vf "drawtext=text='测试文字':fontcolor=0x000080:fontsize=48:x=(w-text_w)/2:y=(h-text_h)/2:box=1:boxcolor=white@0.3:boxborderw=8"
```

---

## 📚 常用字体文件路径（Windows）

### 中文字体
```bash
fontfile=C:/Windows/Fonts/simhei.ttf          # 黑体
fontfile=C:/Windows/Fonts/simsun.ttc           # 宋体
fontfile=C:/Windows/Fonts/simkai.ttf           # 楷体
fontfile=C:/Windows/Fonts/msyh.ttc             # 微软雅黑
fontfile=C:/Windows/Fonts/msyhbd.ttc           # 微软雅黑粗体
fontfile=C:/Windows/Fonts/simli.ttf            # 隶书
```

### 英文字体
```bash
fontfile=C:/Windows/Fonts/arial.ttf            # Arial
fontfile=C:/Windows/Fonts/times.ttf            # Times New Roman
fontfile=C:/Windows/Fonts/calibri.ttf          # Calibri
fontfile=C:/Windows/Fonts/comic.ttf            # Comic Sans
```

---

## 🎨 完整示例：抖音风格花字

```bash
ffmpeg -i input.mp4 -vf "drawtext=text='测试文字':fontfile=C:/Windows/Fonts/msyhbd.ttc:fontcolor=0xFF1493:fontsize=60:x=(w-text_w)/2:y=h-th-80:borderw=5:bordercolor=white:shadowx=2:shadowy=2:shadowcolor=black@0.5" output.mp4
```

**效果**: 
- 文字：测试文字
- 字体：微软雅黑粗体
- 颜色：深粉色（抖音色）
- 大小：60像素
- 位置：底部居中
- 描边：白色，5像素
- 阴影：黑色，半透明

---

## 📊 颜色代码速查表

| 颜色名称 | 十六进制 | RGB | 说明 |
|---------|---------|-----|------|
| 白色 | `0xFFFFFF` 或 `white` | (255,255,255) | 纯白 |
| 黑色 | `0x000000` 或 `black` | (0,0,0) | 纯黑 |
| 红色 | `0xFF0000` 或 `red` | (255,0,0) | 纯红 |
| 绿色 | `0x00FF00` 或 `green` | (0,255,0) | 纯绿 |
| 蓝色 | `0x0000FF` 或 `blue` | (0,0,255) | 纯蓝 |
| 黄色 | `0xFFFF00` 或 `yellow` | (255,255,0) | 纯黄 |
| 紫色 | `0xFF00FF` 或 `magenta` | (255,0,255) | 洋红 |
| 青色 | `0x00FFFF` 或 `cyan` | (0,255,255) | 青色 |
| 橙色 | `0xFF6600` | (255,102,0) | 橙色 |
| 粉色 | `0xFF1493` | (255,20,147) | 深粉色（抖音色） |
| 金色 | `0xFFD700` | (255,215,0) | 金色 |
| 灰色 | `0x808080` | (128,128,128) | 灰色 |

---

## 🎯 位置参数说明

### 绝对位置
```bash
x=10          # 距离左边10像素
y=10          # 距离顶部10像素
x=w-tw-20     # 距离右边20像素（tw=文字宽度）
y=h-th-20     # 距离底部20像素（th=文字高度）
```

### 相对位置（居中）
```bash
x=(w-text_w)/2    # 水平居中
y=(h-text_h)/2   # 垂直居中
```

### 动态位置（动画）
```bash
x='w-mod(t*50,w+tw)'    # 从右向左滚动
y='h-100*sin(t)'        # 上下浮动
```

---

## ⚙️ 常用参数列表

| 参数 | 说明 | 示例值 |
|------|------|--------|
| `text` | 显示的文字 | `'测试文字'` |
| `fontfile` | 字体文件路径 | `C:/Windows/Fonts/msyh.ttc` |
| `fontsize` | 字体大小（像素） | `48`, `60` |
| `fontcolor` | 字体颜色 | `white`, `red`, `0xFF0000` |
| `x` | X坐标位置 | `10`, `(w-text_w)/2` |
| `y` | Y坐标位置 | `10`, `(h-text_h)/2` |
| `borderw` | 描边宽度 | `3`, `5` |
| `bordercolor` | 描边颜色 | `black`, `white` |
| `box` | 是否显示背景框 | `1`（显示）或 `0`（不显示） |
| `boxcolor` | 背景框颜色 | `black@0.5`（半透明黑色） |
| `boxborderw` | 背景框内边距 | `5`, `10` |
| `shadowx` | 阴影X偏移 | `2`, `4` |
| `shadowy` | 阴影Y偏移 | `2`, `4` |
| `shadowcolor` | 阴影颜色 | `black@0.8` |
| `enable` | 显示时间段 | `'between(t,0,10)'` |
| `alpha` | 透明度 | `0.5`（50%透明） |

---

## 🚀 快速使用指南

### 1. 最简单的文字叠加
```bash
ffmpeg -i input.mp4 -vf "drawtext=text='测试文字':fontcolor=white:fontsize=48:x=10:y=10" output.mp4
```

### 2. 带描边的文字
```bash
ffmpeg -i input.mp4 -vf "drawtext=text='测试文字':fontcolor=white:fontsize=50:x=(w-text_w)/2:y=(h-text_h)/2:borderw=3:bordercolor=black" output.mp4
```

### 3. 带背景框的文字
```bash
ffmpeg -i input.mp4 -vf "drawtext=text='测试文字':fontcolor=white:fontsize=50:x=(w-text_w)/2:y=(h-text_h)/2:box=1:boxcolor=black@0.5:boxborderw=5" output.mp4
```

### 4. 抖音风格（粉色+白描边）
```bash
ffmpeg -i input.mp4 -vf "drawtext=text='测试文字':fontcolor=0xFF1493:fontsize=60:x=(w-text_w)/2:y=h-th-80:borderw=5:bordercolor=white" output.mp4
```

---

## 💡 提示

1. **中文字体**: 必须指定中文字体文件（如 `msyh.ttc`），否则中文可能显示为方块
2. **颜色格式**: 可以使用颜色名称（如 `white`）或十六进制（如 `0xFFFFFF`）
3. **透明度**: 使用 `@` 符号，如 `black@0.5` 表示50%透明的黑色
4. **位置计算**: `w`=视频宽度，`h`=视频高度，`text_w`=文字宽度，`text_h`=文字高度
5. **多个文字**: 使用多个 `drawtext` 用逗号分隔，如 `drawtext=...,drawtext=...`

---

## 📝 总结

以上20个模板涵盖了常见的花字效果，包括：
- ✅ 基础文字（白色、红色、黄色等）
- ✅ 描边文字（各种颜色描边）
- ✅ 阴影文字
- ✅ 背景框文字
- ✅ 动画文字（滚动、闪烁）
- ✅ 抖音风格（粉色+白描边）
- ✅ 各种颜色搭配

你可以根据需要选择合适的模板，或者组合多个效果！




