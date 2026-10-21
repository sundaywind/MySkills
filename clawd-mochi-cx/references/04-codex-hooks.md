# 04 - Codex Hook Integration (WiFi)

This is the buyer-facing setup guide for making the WiFi mascot follow Codex.
The device firmware is already complete; this layer only installs the Codex host
adapter and sends `GET /event?s=<state>` to the mascot over the local network.

## What Gets Installed

Copy these files from `assets/` into:

```text
%USERPROFILE%\.codex\hooks\
```

| File | Purpose |
|---|---|
| `clawd-mochi-codex.cmd` | Small Windows launcher used by Codex hooks |
| `clawd-mochi-codex.ps1` | Reads Codex hook JSON, classifies the event, sends WiFi HTTP |
| `hooks.json` | Template hook registration; merge into `%USERPROFILE%\.codex\hooks.json` |

The adapter keeps normal output silent. It writes logs only if the buyer sets
`CLAWD_MOCHI_DEBUG=1`.

## Install Steps

1. Create the hooks folder:

   ```powershell
   New-Item -ItemType Directory -Force "$env:USERPROFILE\.codex\hooks"
   ```

2. Copy the three asset files into that folder.

3. Create a device URL file:

   ```powershell
   Set-Content "$env:USERPROFILE\.codex\hooks\clawd-mochi.url" "http://<device-ip>"
   ```

   Use the numeric IP shown by the mascot or your router, for example
   `http://192.168.1.23`. Numeric IP is recommended on Windows because repeated
   `.local` lookups can be slow.

4. Open the copied `assets/hooks.json` template and replace every
   `__HOOKS_DIR__` with the absolute hooks folder path. In JSON, backslashes must
   be doubled:

   ```json
   "C:\\Users\\your-name\\.codex\\hooks\\clawd-mochi-codex.cmd"
   ```

5. Merge the template's top-level `"hooks"` object into:

   ```text
   %USERPROFILE%\.codex\hooks.json
   ```

   If the file already exists, merge rather than overwrite. Preserve any other
   product hooks the buyer already trusts.

6. Restart Codex, run `/hooks`, and trust the Clawd Mochi hook commands.
   Codex will not run newly added hooks until the user trusts them.

7. Test from PowerShell:

   ```powershell
   & "$env:USERPROFILE\.codex\hooks\clawd-mochi-codex.cmd" -State done
   ```

   The device should show the happy `done` animation, then return to rest.

## macOS / Linux 安装（零依赖，无需 PowerShell）

Mac/Linux 用自带的 **bash + curl + perl** 版适配器 `clawd-mochi-codex.sh`，
开箱即用，不装任何东西。行为与 Windows 版一致（状态映射 + done 回落 + 空闲转
sleep + 关闭 Codex 转 sleep）。

1. 建目录并拷贝两个文件：

   ```bash
   mkdir -p ~/.codex/hooks
   cp clawd-mochi-codex.sh ~/.codex/hooks/
   chmod +x ~/.codex/hooks/clawd-mochi-codex.sh
   ```

2. 写设备地址（数字 IP，看设备开机屏幕或路由器；Mac 也可用 `clawd-mochi.local`）：

   ```bash
   echo "http://192.168.1.23" > ~/.codex/hooks/clawd-mochi.url
   ```

3. 把 `hooks.macos.json` 里的 `"hooks"` 合并进 `~/.codex/hooks.json`。
   **命令里的 `$HOME` 由 shell 自动展开，不用改任何路径。** 若该文件已存在，合并而非覆盖。

4. 重启 Codex，运行 `/hooks` 并信任这些 hook 命令。

5. 测试（应看到 happy 的 done 动画后回到休息脸）：

   ```bash
   printf '{"hook_event_name":"Stop","last_assistant_message":"done"}' | bash ~/.codex/hooks/clawd-mochi-codex.sh
   ```

   排错：`CLAWD_MOCHI_DEBUG=1` 会把每步写到 `~/.clawd_mochi_codex.log`；
   `CLAWD_MOCHI_DRYRUN=1` 只打印判定出的状态、不真正发送，方便验证分类。

> 依赖检查：`bash`、`curl`、`perl` 都是 macOS 自带；`perl -MTime::HiRes -e1`
> 不报错即可。整套逻辑对齐下面的映射表，Win/Mac/Linux 完全一致。

## Event to Expression Mapping

The template intentionally sends all relevant Codex events to one adapter script.
The script performs the semantic classification, so WiFi / wired / BLE use the
same state logic.

| Codex event or tool category | Device state | Sprite |
|---|---|---|
| `SessionStart` | `idle` | `sprite_idle` |
| `UserPromptSubmit` | `thinking` | `sprite_thinking` |
| read/search/fetch/list tools, read-only shell commands | `reading` | `sprite_debugger` |
| apply/edit/write/patch tools, editing shell commands | `coding` | `sprite_typing` |
| shell commands, browser/computer tools, long-running commands | `running` | `sprite_building` |
| `SubagentStart`, task/thread handoff style tools | `delegating` | `sprite_conducting` |
| update-plan / plan-mode style tools | `planning` | `sprite_wizard` |
| `PermissionRequest`, AskUserQuestion, choice prompts before the buyer answers | `waiting` | `sprite_alert` |
| `PreCompact` | `compacting` | `sprite_sweeping` |
| notification-like / MCP / external-service attention events | `notify` | `sprite_beacon` |
| normal `Stop` | `done` | `sprite_happy` |
| explicit tool/subagent failure | `error` | `sprite_confused` |
| idle timer or CLI close watcher | `sleep` | `sprite_sleeping` |

Notes:

- Codex hook payloads require a little classification, so the script also
  inspects shell command text. Read-only commands become
  `reading`; file-changing commands become `coding`; other commands become
  `running`.
- `PostToolUse` repeats the same tool state unless an explicit failure flag is
  present. This keeps the working animation visible until the next real state.
- User-choice tools are the one intentional exception: `PreToolUse` shows
  `waiting`; once the buyer submits a choice, `PostToolUse` returns to
  `thinking` so the mascot no longer looks like it is still waiting.
- `done` is held for about five seconds to match the firmware's happy animation.
- The script filters Codex App internal helper sessions so prompt suggestions,
  titles, and summaries do not flicker the mascot after a real turn ends.
- Codex is not expected to provide a guaranteed close hook, so `sleep` is handled
  by a best-effort CLI close watcher and the idle sleep timer.
- There is no required cloud service. The PC sends one HTTP request to the
  mascot on the same LAN.

## Manual State Tests

Run any of these after installation:

```powershell
& "$env:USERPROFILE\.codex\hooks\clawd-mochi-codex.cmd" -State thinking
& "$env:USERPROFILE\.codex\hooks\clawd-mochi-codex.cmd" -State reading
& "$env:USERPROFILE\.codex\hooks\clawd-mochi-codex.cmd" -State coding
& "$env:USERPROFILE\.codex\hooks\clawd-mochi-codex.cmd" -State running
& "$env:USERPROFILE\.codex\hooks\clawd-mochi-codex.cmd" -State delegating
& "$env:USERPROFILE\.codex\hooks\clawd-mochi-codex.cmd" -State planning
& "$env:USERPROFILE\.codex\hooks\clawd-mochi-codex.cmd" -State compacting
& "$env:USERPROFILE\.codex\hooks\clawd-mochi-codex.cmd" -State notify
& "$env:USERPROFILE\.codex\hooks\clawd-mochi-codex.cmd" -State waiting
& "$env:USERPROFILE\.codex\hooks\clawd-mochi-codex.cmd" -State sleep
```

## Troubleshooting

| Symptom | Check |
|---|---|
| Manual test does nothing | Confirm the device IP in `clawd-mochi.url`, same WiFi/LAN, and test `http://<device-ip>/state` in a browser |
| Hooks do nothing but manual test works | Restart Codex, run `/hooks`, trust the hook entries |
| Codex feels slow on every event | Use a numeric IP in `clawd-mochi.url`; avoid per-event `.local` lookup on Windows |
| Mascot flickers after Codex finishes | Use this CX adapter; it filters Codex App helper sessions and suppresses stale post-stop events |
| `done` disappears too quickly | Ensure the shipped CX script has `$DoneHoldMs = 5200` |

Keep this document buyer-safe: do not ship developer paths, actual private IPs,
debug logs, or local `.codex` trust records.
