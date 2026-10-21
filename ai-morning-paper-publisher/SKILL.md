---
name: ai-morning-paper-publisher
description: "一键抓取微信《AI早报》并进行高级排版重绘、校验当前公网IP，最终一键推送到微信公众号草稿箱。"
---

# ai-morning-paper-publisher

当用户需要发布或推送《AI早报》等公众号文章时使用该技能。此技能集成了公网 IP 查询、防反爬网页抓取、高级暗色卡片样式提取和微信草稿 API 上传。

## 前置要求
1. 脚本会优先从本地 `%USERPROFILE%\.stepclaw\openclaw.json` 读取微信凭证，您也可以使用环境变量配置：
   ```bash
   export WECHAT_APP_ID=YOUR_APP_ID
   export WECHAT_APP_SECRET=YOUR_APP_SECRET
   ```

## 执行流程

大模型应遵循以下三个步骤为用户提供推送服务：

### 步骤 1：查询当前公网 IP 并引导添加白名单
运行工作流脚本的 `get-ip` 阶段：
```bash
python scripts/publish_workflow.py --stage get-ip
```
**模型动作**：获取输出 the IP 地址，以高亮格式告知用户，并提示用户：“请先将此 IP [IP] 添加到微信公众号后台的 IP 白名单中。添加完成后再进行下一步。”

### 步骤 2：获取、美化转换与生成封面图
当用户确认 IP 已加白后，运行 `convert` 阶段抓取并美化 HTML：
```bash
python scripts/publish_workflow.py --stage convert --url [文章URL]
```
**模型动作**：
- 脚本将自动输出美化过的单栏内联样式 HTML 临时文件。
- 如果用户未指定封面图，大模型应使用 `generate_image` 帮用户生成一张高大上的 AI 科技感封面图。

### 步骤 3：一键上传草稿箱
运行 `push` 阶段执行最终上传：
```bash
python scripts/publish_workflow.py --stage push --title "[早报标题]" --cover "[封面图路径]" --author "[作者]" --digest "[摘要]"
```
**模型动作**：输出推送成功的 Media ID，并引导用户去公众号草稿箱完成最终确认与群发。
