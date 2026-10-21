---
name: youdaonote-wiki
version: 1.0.0
description: "有道云笔记知识库管理：创建、查询、摄入素材、归档对话。基于 Karpathy 的 LLM Wiki 模式。触发词：知识库、Wiki、新建知识库、创建 Wiki、初始化 Wiki、素材摄入、知识查询、知识库审计、一致性检查、归档对话、记下来、存入知识库、切换知识库。"
metadata:
  hermes:
    emoji: "📚"
    requires:
      bins:
        - youdaonote
      env:
        - YOUDAONOTE_API_KEY
    tags: [wiki, knowledge-base, research, notes, youdao]
---

# YoudaoNote Wiki — 有道云笔记知识库

在有道云笔记中构建持久化、可复合增长的知识库。
基于 [Andrej Karpathy 的 LLM Wiki 模式](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)。

**核心理念**：传统 RAG 每次查询从零开始检索，知识不复合。Wiki 模式将知识**编译一次、持续维护**——交叉引用已经建好，矛盾已经标记，综合分析反映全部素材。

**分工**：人类策划素材方向、指导分析重点；Agent 负责摘要、交叉引用、归档、维护一致性。

**独特优势**：知识库存储在有道云笔记云端，天然**多端同步、随时可查**，不限于本地开发环境。

## 前置检查

执行任何操作前，先运行 `youdaonote list` 检测 CLI 是否可用：

- **`command not found`** → 提示用户安装 CLI
- **API Key 错误** → 提示用户访问 **https://mopen.163.com** 获取 API Key
- **正常返回目录列表** → 继续执行

## 会话启动协议

每次新会话开始时，必须按下列步骤推进：

### 第一步：定位全局注册表

```bash
youdaonote -s wiki list   # 扫描根目录（只读）
```

查找标题为 `youdaonote-wiki-registry.md` 的笔记：
- **找到** → `youdaonote -s wiki read <registryFileId>` 读取注册表
- **未找到** → 进入第二步（需用户确认重建）

### 第二步：选择目标知识库（A+B 策略）

| 情况 | 策略 | 行为 |
|------|------|------|
| 用户消息含明确知识库名 | B（自动） | 直接从注册表匹配 |
| 上下文有线索 | B（自动） | 选最相关的 |
| 无法判断 | A（询问） | 列出注册表中所有知识库让用户选 |
| 注册表为空 | — | 提示用户先创建知识库 |

## Wiki 文件夹结构

```
<知识库名>/              ← 根文件夹
├── schema.md            ← 结构约定、领域定义、fileId 注册表
├── index.md             ← 内容目录
├── log.md               ← 操作日志（只追加）
├── raw/                 ← 原始素材（immutable）
├── entities/            ← 实体页（人物、组织、产品、工具）
├── concepts/            ← 概念页（主题、技术、方法论）
├── comparisons/         ← 对比分析页
└── queries/             ← 查询归档页
```

## 核心操作

### 1. 列出目录

```bash
# 列出根目录
youdaonote -s wiki list

# 列出子文件夹内容
youdaonote -s wiki list -f <folderId>
```

### 2. 读取笔记

```bash
youdaonote -s wiki read <fileId>
```

### 3. 创建/保存笔记（两步模式）

**Windows 注意**：临时文件使用 `~/AppData/Local/Temp/` 而非 `/tmp/`。

```bash
# Step 1: 写入临时文件
cat > ~/AppData/Local/Temp/wiki-page.md << 'EOF'
# 页面标题
内容...
EOF

# Step 2: 保存到有道云笔记
printf '%s\n' '{
  "title": "page-title.md",
  "type": "md",
  "parentId": "<FOLDER_ID>",
  "contentFile": "C:/Users/Wind/AppData/Local/Temp/wiki-page.md"
}' | youdaonote -s wiki save --json
```

### 4. 更新已有笔记

```bash
youdaonote -s wiki update <fileId> --file ~/AppData/Local/Temp/updated.md
```

### 5. 搜索笔记

```bash
youdaonote -s wiki search "关键词"
```

### 6. 创建文件夹

```bash
youdaonote -s wiki mkdir "文件夹名"
youdaonote -s wiki mkdir "子文件夹" -f <parentId>
```

## 交叉引用

云端笔记不支持 `[[wikilinks]]`，使用以下约定：

- 文中提到其他 Wiki 页面时，使用 **`→ 页面标题`** 标记
- Agent 通过 index.md 或 `youdaonote -s wiki search` 定位被引用页面

## 笔记分类与 parentId 对应关系

| 笔记分类 | parentId 变量 | 说明 |
|----------|---------------|------|
| `raw` | `RAW_ID` | 网页剪藏或手动保存 |
| `entity` | `ENTITY_ID` | 人物、组织、产品、工具 |
| `concept` | `CONCEPT_ID` | 技术、方法论、主题 |
| `comparison` | `COMPARISON_ID` | 对比分析 |
| `query` | `QUERY_ID` | 查询归档 |

## Ingest（摄入素材）流程

1. **捕获原始素材** → 保存到 `raw/`
2. **识别关键实体** → 创建/更新 entity 页
3. **识别关键概念** → 创建/更新 concept 页
4. **建立交叉引用** → 添加 `→` 标记
5. **更新 index.md + log.md**

**防重复规则**：创建/更新前必须先 search 确认是否已存在。

## Windows 特殊处理

- 临时文件路径：`C:/Users/Wind/AppData/Local/Temp/` 或 `~/AppData/Local/Temp/`
- `contentFile` 参数使用正斜杠路径
- 确保 `YOUDAONOTE_API_KEY` 已配置在 `~/.hermes/.env`

## 相关技能

- → youdaonote-clip（网页剪藏）
- → youdaonote-news（资讯推送）
- → obsidian（本地笔记管理）
