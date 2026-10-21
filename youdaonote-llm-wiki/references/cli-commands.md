# YoudaoNote CLI 使用参考

## 常用命令

```bash
# 列出根目录
youdaonote list

# 列出子目录
youdaonote list -f <folderId>

# 读取笔记
youdaonote read <fileId>

# 搜索笔记
youdaonote search "关键词"

# 创建笔记（两步模式）
# Step 1: 写入临时文件
# Step 2: 保存到有道云笔记
printf '%s\n' '{"title":"note.md","type":"md","parentId":"<folderId>","contentFile":"/tmp/note.md"}' | youdaonote save --json

# 更新笔记
youdaonote update <fileId> --file /tmp/note.md
```

## Wiki 专用命令

```bash
# 列出 Wiki 内容
youdaonote -s wiki list
youdaonote -s wiki list -f <folderId>

# 移动笔记到指定文件夹
youdaonote -s wiki move <fileId> <targetFolderId>

# 移动文件夹到另一个文件夹
youdaonote -s wiki move <sourceFolderId> <targetFolderId>

# 重命名笔记
youdaonote -s wiki rename <fileId> <newName>

# 删除笔记
youdaonote -s wiki delete <fileId>

# 创建 Wiki 页面
printf '%s\n' '{"title":"page.md","type":"md","parentId":"<folderId>","contentFile":"/tmp/page.md"}' | youdaonote -s wiki save --json

# 更新 Wiki 页面
youdaonote -s wiki update <fileId> --file /tmp/page.md
```

## Windows 路径注意

- Windows 上 `/tmp` 路径不存在，使用 `~/AppData/Local/Temp/`
- 路径格式：`C:/Users/<username>/AppData/Local/Temp/`

## fileId 说明

- 根目录文件夹 ID：如 `1043514AD6AF4E7FB2E610473CB6F612`
- 子文件夹 ID：如 `8BA18760C0654008B4DC575AAECB3B81`
- 笔记 ID：如 `82E34E1BDF874A06B4ADC9D2D16C4994`

## 从其他 AI 代理复制技能

如果 OpenClaw/QClaw 已安装 YoudaoNote Skills，可直接复制：

```bash
# 复制技能目录
cp -r ~/.openclaw/workspace/skills/youdaonote-* ~/AppData/Local/hermes/skills/note-taking/
cp -r ~/.qclaw/skills/youdaonote-* ~/AppData/Local/hermes/skills/note-taking/

# 配置 API Key
echo 'YOUDAONOTE_API_KEY=your_key' >> ~/AppData/Local/hermes/.env
```
