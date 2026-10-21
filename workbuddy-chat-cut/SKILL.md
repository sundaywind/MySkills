---
name: workbuddy-chat-cut
version: "0.1.0"
display_name: "workbuddy视频剪辑(Chatcut)"
display_name_en: "WorkBuddy Video Editing (ChatCut)"
description: "让 WorkBuddy 连接 ChatCut Desktop，用自然语言完成素材导入、片段剪切与编排、口播剪辑、字幕、配音配乐、转场动效及成片导出。适用于短视频和口播视频制作，具体能力以当前 ChatCut 接口为准。"
description_zh: "让 WorkBuddy 连接 ChatCut Desktop，用自然语言完成素材导入、片段剪切与编排、口播剪辑、字幕、配音配乐、转场动效及成片导出。适用于短视频和口播视频制作，具体能力以当前 ChatCut 接口为准。"
description_en: "Connect WorkBuddy to ChatCut Desktop to import media, cut and arrange clips, edit speech-led footage, add captions, voiceovers, music, transitions and motion graphics, and export videos using natural-language requests. Use for short-form and talking-head video production; available capabilities depend on the current ChatCut API."
---

# workbuddy-chat-cut

本 Skill 负责让助手知道 ChatCut 能做什么，并可靠地调用它。创作判断、口播取舍和视觉设计由助手及独立领域 Skill 负责。

## 能力导航

这是一张能力地图，不是当前可用操作清单。先按类别定位，再从本次 guidelines 查询操作；有些能力会随项目、登录状态、账号或服务变化。

| 类别（--group） | 能做什么 | 常用定位词 |
|---|---|---|
| project | 项目、版本与多时间线 | project / timelines |
| timeline | 放置、移动、切分片段；轨道与标记 | item / track / markers |
| media | 本机导入、网络下载、素材查找与取回 | asset / import_url |
| speech | 转写、定位原话、文字剪辑、停顿清理 | transcript / script |
| captions | 字幕生成、文字、样式、翻译 | captions |
| audio | 音轨分离、剪切平滑、人声处理 | detach_audio / smooth_audio / isolate_voice |
| graphics | JSX 动效、模板、字体、设计风格 | motion_graphic / template / fonts |
| library | 效果、转场、音效、LUT、外部素材 | library / stock_media / shader |
| generation | AI 图片、视频与续写 | submit_image / submit_video |
| voice | 配音、音色、配乐与音效生成 | voice / music / sound |
| avatar | 数字人与视频翻译 | avatar / video_translation |
| delivery | 时间线预览、成片/字幕/剪映导出、任务进度 | preview / export / progress |

运行 capabilities 会把实际返回的操作按以上类别列出，同时标记未返回的类别；不要因为地图里有某项，就假设本次能调用。机器可读导航在 references/capabilities.json。

## 推荐调用流程

统一通过 sh scripts/run.sh 调用；首次执行 sh scripts/run.sh setup。入口自动使用本 Skill 内的 .venv，不用手动激活或选 Python。也可复用 Python 的 Session，不临时重写通信和 JSON 拼装代码。完整用法见 [接入用法](references/usage.md)。

1. **发现**：active 只激活并读项目，不拉取能力。capabilities/describe/instructions/draft 默认复用 state-dir 中的缓存并标记 cached；首次无缓存或 --refresh 时才先激活再拉取能力，激活失败立即停止。切项目/账号或发现能力变化时刷新。首次任务及规则变化后用 instructions 分页读完通用规则，再 describe 所用操作；缓存仅供导航，准备/执行仍使用实时定义。
2. **准备**：常见动作用 recipe；其他动作用 prepare 的参数文件、--set、--text、--file 或 --json-string。脚本负责嵌套结构、读文件和转义；不猜用户意图、素材 ID、轨道或时长。
3. **校验**：prepare 连接真实 ChatCut，依据当前 inputSchema 校验，生成绑定项目与接口指纹的计划。draft 只生成必填项草稿，null 占位必须填写，不代表已经合法。
4. **执行**：run 计划；修改操作加 --write（代表用户已授权任务，不另设逐步审批）。运行时重新读取接口并检查指纹、参数和目标项目；有 validateOnly 时默认先预检，成功后提交一次。call 是同样检查的一步式入口。
5. **核实**：保留返回的 requestId、计划和 receipt。接口返回不等于异步生成/导出完成；按实时接口查询进度或预览实际结果。本地音视频交付前执行 scripts/wait_export.sh（参数见接入用法第 8 节）；检查失败不交付，没有本地导出状态接口时不冒用生成任务查询。

新建/切换项目后，先 ready --project 实际项目ID，确认可读取再写入；失败可重新连接做只读检查，不能重放建项目或添加素材。ready 只证明检查时可读，不保证下一次写入不会断线。

**先定尺寸，再摆内容**：create_project 使用 compositionWidth/compositionHeight，不是 width/height；返回成功也要用 verify-size 读回确认活动时间线的尺寸。需要修正时用 recipe set-size，直接传字段给 manage_timelines，不套 json。已有内容改比例默认拦截；任务明确允许时才加 --allow-layout-change，改后逐一检查字幕/浮层位置，不自动删除重建。尺寸不符或读回失败时停止后续摆素材。

## 参数封装

- recipe import：一个或多个本机路径 → 导入参数，自动绝对路径与文件存在检查。
- recipe place：素材、轨道、类型、起始帧、持续帧 → 时间线 adds。
- 正常速度音视频优先 recipe place-media：另传准确源时长、时间线 fps、可选 source-in-us，计算剩余源时长可容纳的整帧数，超界拒绝，不自动截短。frames 可先离线算；变速/循环另按实时说明处理。
- recipe transcribe：明确 --role speech 才为指定素材组装 trigger_transcript 的 asset 参数；纯音乐不主动转写。
- recipe update-item：片段 ID 和字段 → updates，避免手写批次外壳。
- recipe motion：代码文件和属性元数据 → 内联 JSX 创建参数。
- recipe update-code：素材 ID、代码文件、可选属性 → 自动编码更新需要的 JSON 字符串。
- recipe set-size：活动时间线完整 ID、宽、高 → 尺寸更新计划；执行时检查原有内容，提交后读回核对。
- recipe delete-item：时间线片段 ID → deletes 中只含 id（不是删除媒体池素材）。recipe delete-attached：效果/转场 ID 和准确的 pixel-effect/pixel-transition → id + type。
- 通用 prepare/call 覆盖实时返回的其他操作；--json-string 将 JSON 文件编码成字符串，--file 读取原文，不手工多层转义。

这些封装仍必须通过实时 schema 校验；ChatCut 改接口时明确拒绝，不悄悄换旧字段重试。
动效可编辑属性的每项目前需要 key、type、label、defaultValue；以实时 schema 为准，缺项会在提交前给出如 /properties/0/label 的路径，不代填创作内容。

## 字幕与素材结果核对

字幕 enable 在已有字幕时只恢复显示，不代表重新派生新源轨。先放齐所有口播、确认其转写完成，再开字幕；已有字幕时不要开关反复重试。用 check-captions 显式传口播/纯音乐的媒体源轨完整 ID，检查缺失、隐藏、空字幕及音乐污染；不通过就停，不自动把素材搬到 A1。覆盖通过也不等于每句完整或识别准确。
纯音乐可能在导入后自动得到错误转写；不主动 trigger 并不能阻止这一点。确认来源后可用 recipe hide-music-captions 生成只隐藏对应字幕轨的计划，不静音/隐藏音乐素材。混有人声与音乐的同一源轨不能整轨当 BGM 隐藏。
搜索 orientation 仅作为请求条件，结果须用 filter-orientation 检查宽高；无尺寸视为待核实。下载后还需核对实际媒体尺寸及旋转方向，不把搜索元数据当作文件证明。具体命令见接入用法第 10 节。

## 可靠性边界

- JSON Schema 校验使用 jsonschema 库，覆盖必填、类型、枚举、范围、组合约束与本地引用；禁止自动联网拉取外部 schema。schema 未表达的项目状态/业务限制仍靠 ChatCut 预检和结果检查。
- 保持同一个 --state-dir。同一计划重复 run 返回已记录结果，不再次提交；超时、断线、部分错误或中断会阻止同一 requestId 重放。先检查实际状态，再决定后续操作，不生成新 ID 盲目重试。
- 项目有 pending/unknown 写入时，也拦截新 ID 的后续写入，允许只读核查。unknown 只有在核对确切素材/片段 ID、路径及关键字段后，才能用 reconcile 记录结论和只读证据。部分成功、结果不明或后台仍可能继续时保持拦截；“暂时查不到”不能判定未执行。流程见接入用法第 9 节。
- 所有写入前核对目标项目；无活动项目时可查能力，但不执行项目操作。检查与提交之间仍有用户手动切项目的间隙，不能宣称原子绑定。
- 预检只用当前 schema 明确提供的 validateOnly；库音效等不支持的情况不强套。它不能保证网络、渲染、额度和服务端业务检查都成功。
- edit_item 的批量是原子提交；相关编辑放一起并预检，无关的效果/位置修改分开。脚本不自动拆批或整批重试，避免改变编辑语义或重复写入。
- 辅助连接也要遵循宿主权限。若改用宿主原生 MCP execute，必须先核对相同实时定义；它不会自动经过本脚本的校验和防重复记录。
- Desktop 的 UI 供用户查看，不通过点击或聊天框代替接口；本机素材不会自动上传到网页版。

## 发布包结构

ZIP 根目录直接包含 SKILL.md、scripts/ 和 references/，不再套 workbuddy-chat-cut/ 外层目录。scripts/ 和 references/ 内只放文件，遵守平台两级目录限制。发布包不包含本机 .venv、.chatcut、__pycache__ 或测试内容；解压后首次使用仍运行 sh scripts/run.sh setup 创建本机环境。

## 工具组成

- run.sh：初始化独立环境，统一调用和 Python 入口。
- wait_export.sh / wait_export.py：本次导出的文件稳定性、媒体与时长验证；不重新发起导出。
- chatcut.py：统一命令入口与可读结果。
- chatcut_client.py：能力目录、校验、项目绑定、计划、调用记录和常用方法。
- chatcut_params.py：类型明确的参数输入与文件序列化。
- chatcut_stdio.py：会话握手、超时、通信和进程清理。
- chatcut_errors.py：完整服务端错误保留、字段问题提取；界面摘要不替代完整调用记录。
- chatcut_checks.py：字幕来源覆盖、结果宽高筛选、正常速度可用帧数计算。
- dump_guidelines.py：需要完整规范落盘、全文检索和版本对比时使用。
