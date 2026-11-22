# 功能说明（开发者）

## 1. 自动化工作流（`views/AutomationWorkflow.tsx`）

- 输入平台视频链接或行业关键词。
- 调用后端创建任务：解析文案 →（可选）合规 → 口播素材 → 按所选平台串行发布。
- 同页集成「截流找客户」开关，与 `pixelle_wrapper` 的 `/api/intercept/*` 交互。

## 2. 文案与人设（`views/CopywritingProduction.tsx`）

- 配置公司 / 卖点 / 微信号等字段，写入 `localStorage`，供自动化与截流合并使用。
- 仓库内 `config.yaml` 的 `persona` 仅为默认模板，真实微信号应只存在于本机客户端配置。

## 3. 合规检测（`views/ComplianceStation.tsx` + `ai_pipeline/compliance_checker.py`）

- 检测私域引流词、敏感表达等，支持自定义补充规则。

## 4. 口播与成品（`OralBroadcastDetail` / `FinishedMaterial`）

- 上传形象、音频或 TTS，触发 RunningHub / Pixelle 生成。
- 成品页支持字幕轴、封面文案与再次合成，供分发中心使用。

## 5. 分发中心（`views/DistributionCenter.tsx`）

- 平台：`douyin` / `kuaishou` / `xhs` / `sph`（视频号走 `publish/`）。
- 登录态保存在本机 `browser_data`（已在 `.gitignore`，勿提交）。

## 6. 截流找客户（`test_intercept_selenium.py`）

- Selenium 驱动 Chrome，按行业词浏览内容流。
- 评论意向词粗筛 + 可选大模型二判。
- 与 HF 自动回复互斥，避免同一 Chrome 用户目录并发。

## 7. 可选账号门禁（`components/StartupLoginGate.tsx`）

- 仅当构建时设置了 `VITE_ACCOUNT_API_BASE` 才启用。
- 开源默认关闭，便于本地直接使用。
