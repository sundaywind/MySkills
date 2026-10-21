---
domain: x.com
aliases: [twitter, X, 推特]
updated: 2026-09-29
---
## 平台特征
- 搜索页 URL：`https://x.com/search?q=<urlencoded>&f=live`（最新）/ `f=top`（热门）/ `f=user` / `f=media`。
- 搜索**必须登录**，未登录会跳登录墙。CDP 直连用户浏览器通常已登录。
- 中文关键词命中松散，X 会返回大量只含部分词的相关内容；用英文词（如 `Qwen Book`、`Googlebook`）或加英文引号做精确短语时召回质量明显更高。
- 搜索页一次只渲染约 7 条 `article[data-testid=tweet]`，`/scroll?direction=bottom` 对搜索页**无效**（仍为 7 条）。要多拿结果应换关键词/换 `f=` 排序，或改用多个 tab 并行搜不同词。

## 有效模式
- 结构化提取（已验证可用）：
  ```js
  document.querySelectorAll("article[data-testid=tweet]") →
    div[data-testid=tweetText].innerText（正文）
    time[datetime]（时间）
    a[href*="/status/"]（推文链接）
    div[data-testid=User-Names]（作者，可能为空）
  ```
- 多关键词并行：一次 `/new` 开 3–4 个 tab，间隔 2s，再统一 `/eval` 提取。

## 已知陷阱
- **本地 HTTP_PROXY 会劫持 curl**：环境里 `http_proxy=127.0.0.1:3605`，直接 `curl http://localhost:3456/...` 会返回 `upstream connect failed (os error 10061)`。必须加 `--noproxy '*'`，并用 `127.0.0.1` 而非 `localhost`。
- **check-deps 启动的 detached proxy 会随 bash 命令结束被回收**：跨 Bash 调用会连不上（exit 7）。解决：用 `run_in_background` 长期跑 `node scripts/cdp-proxy.mjs --browser chrome`，跨轮次稳定复用。
