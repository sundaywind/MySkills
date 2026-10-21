# 接入用法

从 Skill 目录执行下列命令。首次只需初始化一次（电脑需有 Python 3.10+，安装依赖需要联网）：

```sh
sh scripts/run.sh setup
sh scripts/run.sh doctor
```

之后统一用 sh scripts/run.sh，不用激活环境，不用选 Python。调用自动使用 **Skill 文件夹内 .venv/bin/python**，不依赖工作区旧的 .chatcut-venv，也不修改系统 Python。缺环境/依赖时会提示初始化命令，不会静默安装。
如默认 python3 太旧，初始化时指定：CHATCUT_BOOTSTRAP_PYTHON=/完整路径/python3 sh scripts/run.sh setup。
换电脑或移动安装目录后重新初始化，勿复制 .venv；压缩包不携带它。遇到已有环境路径失效时，将该 Skill 的 .venv 改名备份后重新 setup。
从其他目录调用时使用 run.sh 的完整路径；它仍定位自身的 .venv，不会切换调用者的工作目录。
--state-dir 和 --timeout 是全局选项，放子命令前；同一任务保持同一工作目录或显式固定 state-dir。

## 1. 先理解能力

```sh
sh scripts/run.sh active
sh scripts/run.sh capabilities
sh scripts/run.sh capabilities --group speech
sh scripts/run.sh capabilities --search caption
sh scripts/run.sh instructions
sh scripts/run.sh instructions --catalog .chatcut/catalog.json --offset 3000
sh scripts/run.sh describe edit_item
sh scripts/run.sh describe edit_item --output edit-item-definition.json
```

active 只读当前项目，不获取 guidelines。导航命令 capabilities/describe/instructions/draft 默认复用当前 state-dir/catalog.json，显示 source=cached、capturedAt 和路径，不冒充实时能力；无缓存时才连接并获取完整规范。capabilities --refresh 强制刷新，切项目/账号或能力变化时使用；--refresh 与 --catalog 不混用。缓存损坏时也可显式刷新重建。
capabilities 给能力地图和该次目录里的操作。describe 给单项完整操作说明、必填项及 inputSchema。
通用 instruction 完整留在 catalog.json，不再随导航、describe 和 draft 重复打印。instructions 默认每页 3000 字符（最多 4000），按 nextOffset 继续，直到 null；后续页指定同一 --catalog，避免跨版本拼页。首次任务及规则变化后读完通用说明，不用导航摘要替代规则。describe 只输出所用操作的完整定义；定义特别长时用 --output 保存，再按字段读取文件。
不要把目录中未返回的能力补成“可用”。

在线结果缓存到 .chatcut/catalog.json，供减少重复读取：
```sh
sh scripts/run.sh capabilities --catalog .chatcut/catalog.json
sh scripts/run.sh describe edit_item --catalog .chatcut/catalog.json
```

显式 --catalog 标记 offline，自动复用标记 cached，都只供导航。prepare/recipe/run/call 不支持缓存执行，仍取实时定义并校验；后台可能仍全量获取，未假装服务端支持增量接口。不要直接调用原生 get_guidelines 再把整份返回塞进模型上下文，使用此入口把完整定义留在本地。
多个目录不要混用调用记录；真实项目标识使用 active 返回的完整 ID。无活动项目时请用户在 Desktop 打开项目，再继续。
底层也会在首次 get_guidelines/execute 前自动激活；激活报错不会继续请求能力。新建或切换项目后先运行 sh scripts/run.sh ready --project PROJECT_ID；这是只读 read_project 加前后项目核对，不自动重试。如果当前 read_project 需要参数，先 describe，再用 ready --params 文件传入。

## 2. 常见动作不拼 JSON 外壳

先生成可查看、可复用的计划；以下 PROJECT_ID、ASSET_ID、ITEM_ID 等须替换为实际返回值。

```sh
sh scripts/run.sh recipe import --project PROJECT_ID --path "/素材/视频.mp4" --output import-plan.json
sh scripts/run.sh recipe place --project PROJECT_ID --asset ASSET_ID --track V1 --type video --start 0 --duration 90 --output place-plan.json
sh scripts/run.sh recipe update-item --project PROJECT_ID --item ITEM_ID --fields changes.json --output update-plan.json
sh scripts/run.sh recipe motion --project PROJECT_ID --code title.jsx --metadata title.json --output motion-plan.json
sh scripts/run.sh recipe update-code --project PROJECT_ID --asset ASSET_ID --code title.jsx --output code-plan.json
```

changes.json 只写要改的字段，例如 {"left":80,"top":300}；updates 数组和 id 由脚本组装。
motion 的 metadata 是当前创建接口所需的 name/尺寸/时长/属性；不内置版式或替你写创意。
code 文件内容自动内联；update-code 自动构造并转义 json 字符串，包含中文、引号、换行也不需手工处理。
place 的 start/duration 使用帧；它只放置已有素材，不自动选轨道、剪辑点或素材。
以上方法只生成计划，不实际导入/放置/修改项目。

### 先确定画布，再摆素材和浮层

create_project 的真实尺寸字段是 compositionWidth/compositionHeight；即使参数被接受，也不能当作目标时间线已应用尺寸。新建项目并在 Desktop 打开后，先 ready，然后按 read_project 返回的完整活动时间线 ID 核对：

```sh
sh scripts/run.sh verify-size --project PROJECT_ID --timeline TIMELINE_ID --width 1080 --height 1920
# 不匹配时才准备修正（不是重建项目）：
sh scripts/run.sh recipe set-size --project PROJECT_ID --timeline TIMELINE_ID --width 1080 --height 1920 --output size-plan.json
sh scripts/run.sh run size-plan.json --write
```

set-size 组装的是 manage_timelines 的 action=update、timelineId、compositionWidth、compositionHeight，都是直接字段，没有 json。不要将 edit_project/edit_asset 的 JSON 字符串写法套到 manage_timelines。
执行前会只读检查当前活动时间线；已有时长、字幕或无法确认空白时默认拒绝。用户任务明确包含调整现有布局时，run/call 可加 --allow-layout-change；这不是自动适配保证。修改后自动读回尺寸，compositionVerification.ok=false 时 CLI 非零退出，保留修改已返回的记录，不重发。
尺寸核对通过后再摆字幕、人名条、动效等。改过非空时间线时还须检查这些元素的尺寸和位置；不要自动删除重摆。verify-size 针对活动时间线，其他时间线需先切换；只保证检查时刻，不提供跨调用原子保证。

### 删除对象分清类型

```sh
sh scripts/run.sh recipe delete-item --project PROJECT_ID --item CLIP_ID --output delete-clip.json
sh scripts/run.sh recipe delete-attached --project PROJECT_ID --item EFFECT_ID --type pixel-effect --output delete-effect.json
```

delete-item 生成 deletes:[{id:CLIP_ID}]，不能加 --type video 等媒体类型。delete-attached 仅接收 pixel-effect 或 pixel-transition，生成 id + type。这里删除的是时间线实例；媒体池素材删除是 edit_asset 的另一个操作，不混用 ID。

### 动效属性完整示例

metadata 中 properties 的一项可写成：

```json
{"key":"title","type":"text","label":"标题","defaultValue":"示例标题"}
```

这四个字段按当前真实 schema 都是必填。没有可编辑属性时可以不传整个 properties 数组；不要传半成品属性。脚本在 prepare/recipe 阶段校验；若缺字段还进入服务端才报错，先确认是否绕过 run.sh/Session 使用了原生 MCP，并核对本次实时 schema，不盲试第二次。

## 3. 其他操作的通用输入

简单参数不写整段 JSON：

```sh
sh scripts/run.sh prepare read_captions --project PROJECT_ID --json-string json=caption-query.json --output captions-plan.json
sh scripts/run.sh prepare edit_project --project PROJECT_ID --text action=update --json-string json=project-changes.json --output rename-plan.json
sh scripts/run.sh prepare apply_script --project PROJECT_ID --file timelineMd=timeline.md --output speech-plan.json
sh scripts/run.sh prepare local_export --project PROJECT_ID --text format=video --text outputPath=example.mp4 --set fps=30 --output export-plan.json
```

- --set FIELD=JSON_VALUE：数字、布尔、数组、对象；字符串请用 --text。
- --text FIELD=TEXT：普通字符串。
- --file FIELD=PATH：读取 UTF-8 原文，适合 JSX、台词。
- --json-file FIELD=PATH：读取 JSON 对象/数组等作为字段值。
- --json-string FIELD=PATH：读取合法 JSON，再编码为 API 所需的字符串，避免双重转义。
- --params PATH：已有完整参数文件。其他字段选项可以覆盖这个基础对象；同次字段选项之间重复或父子覆盖会报错。
- 嵌套字段可用 JSON Pointer，例如 --set /adds/0/startFrame=90；数组按序填写，不跳下标。
- 不自动猜时间单位、填素材 ID、修改字符串为数字、补不存在字段或套用旧版别名。

想先看到需要填什么：

```sh
sh scripts/run.sh draft create_motion_graphic_from_code --output params.json
sh scripts/run.sh prepare create_motion_graphic_from_code --project PROJECT_ID --params params.json --output plan.json
```

draft 的 null 是待填写，不是合法默认值；遇到分支/无法表达的必填条件会留给完整 schema 和 prepare 校验。

## 4. 执行与防重复

```sh
sh scripts/run.sh run place-plan.json --write
sh scripts/run.sh run captions-plan.json
sh scripts/run.sh call read_project --project PROJECT_ID
```

--write 只在已获用户任务授权时使用，不表示需要每个小步骤再问用户。
未知操作保守视为可能写入；优先依据当前 MCP readOnlyHint 判断。
run 检查计划内容、项目、当前接口指纹和服务；计划被修改或定义变化时拒绝，重新 prepare。
默认 --preflight auto：当前操作提供 validateOnly 时先预检，再正式提交；库音效 add 不支持它，不强套。
--preflight require 要求预检可用；--preflight skip 显式跳过服务端预检，但仍做本地 schema 校验。
预检返回 isError 或明确的 validation.isValid/valid/isValid/success=false 或失败状态时，不提交正式操作。

同一计划在同一个 state-dir 再 run，只返回已有结果，不再 execute。
超时、断线、进程中断、工具错误可能发生在部分写入之后；记录会阻止盲目重放，不自动重试写入。
call 会自动保存计划到 .chatcut/plans；发生不确定结果时不要再次 call（会生成新请求 ID），先查已生成计划和 receipt。
同一 state-dir 内出现结果未知写入时，同项目的新计划 ID 也会被拦截，直到完成显式核查。原生 MCP 调用或不同 state-dir 不在这个保护范围内；并发的不同请求不是全局幂等，不要宣称服务端 exactly-once。

```sh
sh scripts/run.sh receipt REQUEST_ID
```

receipt 保存完整结果；图片自动保存成独立文件，长文本输出会提示完整记录的位置。
工具错误和预检错误也保留完整原始响应（rawError/rawResponse/preflightRaw），不因屏幕摘要截断而丢失。输出含操作名、可解析的字段路径和 receiptPath；连接阶段的工具错误保存到 state-dir/errors。解析不到字段就明确保留原文路径，不猜缺哪个字段。若服务端本身已经截断，客户端无法补回未收到的内容，可用 describe/dump_guidelines 定位。
state=returned 仅说明这次接口返回成功，不能证明异步任务完成或视觉/音频正确。
即使写入后项目复核失败，也保留已返回结果并警告，不重复执行。

## 5. Python 直接复用

用于复杂参数批次时，直接复用库，不再造一套执行器。使用 sh scripts/run.sh python /完整路径/你的脚本.py 启动，仍共用同一个环境：

```python
from chatcut_client import Session

with Session(state_dir="/任务目录/.chatcut") as chatcut:
    project_id = chatcut.active["projectId"]
    # 这里应与任务开始时记录的目标 ID 核对，不静默跟随用户切换。
    plan = chatcut.place(
        project_id=project_id, asset_id="实际素材ID", track_id="V1",
        kind="video", start_frame=0, duration_frames=90,
    )
    # 保存 plan 后再执行；实际写入必须在用户任务授权范围内。
    from chatcut_client import write_json
    write_json("place-plan.json", plan, exclusive=True)
    result = chatcut.run(plan, allow_write=True)
```

模块在 scripts/ 中，可将这个目录加入 Python 搜索路径。Session 保持同一个连接，退出时清理进程。
生产使用要保存 plan；run 在提交前会自动建立调用记录。

## 6. 无法靠参数校验保证的事

当前 edit_item 的部分嵌套 schema 很宽松，项目 ID/素材存在、轨道重叠、内层业务字段等仍依赖服务端预检。
json 字符串内部没有完整 schema 时，只能保证它是有效 JSON，不能保证里面的业务字段都合法。
format 使用库内已支持的检查器；未知格式标签只是 schema 注释，不提供额外格式保证。
网络断线、额度不足、渲染失败、平台能力变化及用户并发切项目均不能保证“一次成功”。
目标是消除重复拼装和可提前检测的错误，并且一次调用结果不明时不产生重复修改。

## 7. 连接与诊断

ChatCutStdio 依次查 CHATCUT_MCP_COMMAND、CHATCUT_MCP_CONFIG（默认 ~/.workbuddy/mcp.json）、本机 ChatCut wrapper、PATH。
不使用 shell 执行命令字符串，不打印配置中的环境变量；每次 RPC 有超时，包含 stdin 写入阶段。
连接器权限拒绝时遵循宿主审批，不借辅助脚本规避。
dump_guidelines.py 仍可用于完整规范落盘和版本比较，不是另一套操作清单。


## 8. 等待本地音视频导出

local_export 返回 outputPath/taskId 只表示排队，不代表文件写完。先 describe 检查实时能力：若当前接口明确支持该本地导出任务的状态查询，优先确认完成，再做文件检查；不要把云端任务或生成任务查询套到本地导出。
最近核验的 track_progress 只支持 generation/transcription，没有本地导出状态查询。因此下面的脚本使用文件验证兜底，不伪装成服务端完成确认。

```sh
sh scripts/wait_export.sh --receipt .chatcut/receipts/REQUEST_ID.json --expected-duration 120 --timeout 600
# 等价：sh scripts/run.sh wait-export --receipt .chatcut/receipts/REQUEST_ID.json --expected-duration 120
```

REQUEST_ID 使用本次 run/call 返回值；预期秒数来自目标时间线或导出范围，不能取待验文件的时长反过来证明它完整。脚本从 receipt 取真实路径，拒绝旧文件，默认连续 10 秒无大小/时间变化后，用 ffprobe 扫描数据包并验证流和时长（默认容差 0.5 秒）。检查期间继续变化会重新等待。
电脑需有 FFmpeg 的 ffprobe；找不到会明确报错，也可 --ffprobe /完整路径/ffprobe 指定。不会自动安装或跳过检查。
仅适用 .mp4/.mov/.mp3/.wav；字幕、XML、剪映草稿走各自格式验证，不用此脚本。
只有退出码为 0、ok=true 才继续复制/导入/交付。超时、时长不符或媒体损坏时返回非零，不重新发起导出。脚本本身不复制、不修改文件。
file_verified 是本地文件检查通过，不是服务端完成保证，也不是逐帧解码验证；若需要服务端确定完成但无查询能力，应请用户核对 Export History。即使检查通过，也不要声称网络/后台状态得到保证。

## 9. 写入掉线后的核对

1. 不重新 call，也不重新创建项目；先 receipt 原请求ID，保留原计划和结果未知记录。
2. 重新连接同一项目，只读核查：用 describe 选择 read_project、browse_assets 或 inspect_item 等实时可用的只读操作；通过 call 执行并保留证据 requestId。核对原计划的具体路径、素材/片段 ID、轨道、时间位置等，不只匹配名字。
3. 证据足以证明全部已执行，记录 applied；只有能排除后台仍在执行、明确证明完全未执行，才记录 not-applied。部分成功、暂时查不到或无法确认时停下向用户说明，保留拦截。

```sh
sh scripts/run.sh reconcile ORIGINAL_REQUEST_ID --evidence READ_REQUEST_ID --outcome applied --note "核对到素材/片段具体 ID，路径和轨道位置与原计划一致"
```

reconcile 不连接、不提交、不伪造原操作成功返回，只保存调用者明确核对的结论。它验证证据为掉线后、同服务同项目的成功只读记录，但不会替你推断业务匹配；核对责任仍在调用者。
原请求始终禁止重放；applied 后继续后续工作，不再添加同一素材。not-applied 后若仍需执行，才重新 prepare 新计划。pending 可能是仍运行或崩溃中断，不能用此命令解除，先确认进程和实际项目状态，勿删记录绕过。

## 10. 字幕来源、方向和帧数检查

### 字幕必须覆盖预期口播源轨

源轨 ID 来自项目/片段检查，不是字幕轨 ID，也不是 A1 这样的显示名。明确分清口播与纯音乐；同一混合轨不能同时标为两种角色。
字幕尚未建立时，先放齐口播，再确认每个口播素材转写完成，然后 enable，最后 check-captions。已有字幕时，enable/disable 不会保证重新派生新轨，核对失败应停止并检查实际来源，不自动搬轨或重建字幕。

```sh
sh scripts/run.sh recipe transcribe --project PROJECT_ID --asset SPEECH_ASSET_ID --role speech --output transcribe-plan.json
# 执行后按实时 track_progress 的 target=transcription 查询完成状态；不能刚排队就开字幕。
sh scripts/run.sh check-captions --project PROJECT_ID --speech-track SPEECH_SOURCE_TRACK_ID --music-track MUSIC_SOURCE_TRACK_ID
```

多个口播源轨重复 --speech-track；多个音乐源轨重复 --music-track。检查按 captions.tracks 的 sourceTrackId、role、cardCount 和可见性进行，卡片分页不会被误当作全部字幕；本检查不证明每句话完整，仍需核对文字/时间范围。失败输出具体缺失/隐藏/空的源轨以及污染字幕轨 ID，退出非零，不写项目。
trigger_transcript 当前只接受 asset；不要照搬其他操作的 assetId。recipe transcribe 拒绝 --role music；它不会也不能关闭导入时可能自动触发的转写。
如果纯音乐已产生乱码，先确认源轨确为纯音乐，再生成隐藏对应字幕轨的计划：

```sh
sh scripts/run.sh recipe hide-music-captions --project PROJECT_ID --speech-track SPEECH_SOURCE_TRACK_ID --music-track MUSIC_SOURCE_TRACK_ID --caption-track MUSIC_CAPTION_TRACK_ID --output hide-music-captions.json
```

此方法先读当前字幕并核对来源，只组装 edit_captions/action=track/visible=false；没有静音音乐、移动轨道或修改原始转写。执行后再次 check-captions。不能因文本像乱码或语言标记英文就猜它是 BGM。

### 筛选搜索返回的实际宽高

搜索 orientation=vertical 并不替代结果验证。保存结果后，明确指定实际结果数组路径（JSON Pointer），不同返回结构不要猜：

```sh
sh scripts/run.sh filter-orientation --input search-result.json --items-path /results --orientation vertical --output vertical-results.json
```

输入本身为数组则省略 --items-path；若是调用 receipt，可以指定 /result/structuredContent/实际数组字段。每个结果需提供 width/height；缺失/非法尺寸归入 unknown，不算通过。输出保留 accepted 完整条目，屏幕仅显示数量；没有合格结果则非零退出。下载后再用文件探测核对实际尺寸、旋转和显示宽高，尤其不能把横屏文件自动裁切当作满足竖屏素材要求。

### 使用源时长向下取整，不四舍五入

```sh
sh scripts/run.sh frames --source-duration 10.056 --fps 30 --requested 302
# 返回 maxFrames=301，ok=false；不会悄悄将请求改成 301。
sh scripts/run.sh recipe place-media --project PROJECT_ID --asset ASSET_ID --track TRACK_ID --type video --start 0 --duration 301 --source-duration 10.056 --fps 30 --source-in-us 0 --output place-plan.json
```

source-duration 是通过 inspect_asset/源文件探测得到的准确源时长（秒），fps 是时间线帧率，不是源视频帧率，可用 30000/1001。source-in-us 是源入点整数微秒。最大帧数=floor((源时长-源入点秒数)×时间线fps)，仅适用正常速度非循环音视频。计算器不自动查询素材，也不证明调用者提供的元数据正确；不要拿界面上已四舍五入的时长当作精确值。
place-media 在生成计划前检查上限并设置 sourceIn；超过则拒绝。缩短会影响剪辑意图，由调用者明确调整，脚本不静默改变。

### 批量操作不要靠失败试参数

edit_item 一批里的 adds/updates/deletes 按接口原子提交。相关操作保持同批，并利用默认 validateOnly 预检；无关的加效果与改位置分开准备。脚本不自动拆批，也不自动重放失败批次。网络掉线或结果不确定继续按第 9 节核对；原子语义不是盲重试许可。
