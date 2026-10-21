---
name: clawd-mochi-cx
description: >
  Buyer-facing setup and builder reference for the WiFi "Clawd Mochi CX" Codex
  edition: an ESP32-C3 + ST7789 desk mascot that mirrors Codex CLI/App activity
  as 13 pixel-art sprite expressions over WiFi HTTP hooks. Use this skill when
  setting up, installing, explaining, troubleshooting, or customizing the Codex
  WiFi package, including hooks.json, clawd-mochi-codex.ps1, device IP setup,
  /hooks trust, event-to-expression mapping, firmware behavior, or owner
  onboarding for the WiFi version.
---

# Clawd Mochi CX - WiFi Codex Edition

This package is the Codex-facing skill for the **WiFi** version of Clawd Mochi.
The firmware is already the new 13-expression sprite build; the only Codex-specific
layer is the host hook adapter under `assets/`.

Use this skill to help an owner go from "device is flashed and on WiFi" to
"Codex changes the mascot face automatically."

## Quick Setup Path

> **先判断平台，再选安装路径。** 你通常能直接从运行环境得知用户系统
> （`Platform: win32` = Windows，`darwin` = macOS）——**能判断就自动选择，
> 不用多问**；实在拿不准再问一句「你用的是 Windows 还是 macOS？」。
> - **Windows** → 用下面默认步骤（`clawd-mochi-codex.cmd` + `.ps1` + `hooks.json`）。
> - **macOS / Linux** → 改用 `clawd-mochi-codex.sh` + `hooks.macos.json`（见本节末的
>   macOS 短版，或 `references/04` 的「macOS / Linux 安装」）。

For installation, read and follow `references/04-codex-hooks.md`.

The short version (Windows):

1. Copy `assets/clawd-mochi-codex.cmd`, `assets/clawd-mochi-codex.ps1`, and
   `assets/hooks.json` into `%USERPROFILE%\.codex\hooks\`.
2. Edit the copied `hooks.json` template by replacing `__HOOKS_DIR__` with that
   absolute hooks path, using escaped backslashes.
3. Merge the template's `hooks` object into `%USERPROFILE%\.codex\hooks.json`.
4. Put the device URL in `%USERPROFILE%\.codex\hooks\clawd-mochi.url`, for
   example `http://192.168.1.23`.
5. Restart Codex, run `/hooks`, trust the Clawd Mochi hooks, then test:
   `clawd-mochi-codex.cmd -State done`.

**macOS / Linux（零依赖 bash 版，无需 PowerShell）：** 改用 `assets/clawd-mochi-codex.sh`
和 `assets/hooks.macos.json`——把 `.sh` 拷进 `~/.codex/hooks/` 并 `chmod +x`，把
设备地址写进 `~/.codex/hooks/clawd-mochi.url`，再把 `hooks.macos.json` 的 `hooks`
合并进 `~/.codex/hooks.json`（命令里的 `$HOME` 自动展开，无需改路径）。详见
`references/04-codex-hooks.md` 的「macOS / Linux 安装」一节。

The guide intentionally uses placeholders like `%USERPROFILE%` and
`192.168.1.23`; do not include local developer paths, IPs, logs, or build history
when repackaging for buyers.

## Codex State Model

The WiFi firmware accepts:

`idle`, `thinking`, `reading`, `coding`, `running`, `delegating`, `planning`,
`waiting`, `compacting`, `notify`, `done`, `error`, `sleep`.

The Codex adapter keeps the hook surface small: all common Codex hook events call
one PowerShell script, and the script classifies the event/tool into the right
state. This avoids one-hook-per-expression drift.

| Codex source | Device state | Sprite |
|---|---|---|
| `SessionStart` | `idle` | idle bob |
| `UserPromptSubmit` | `thinking` | particle swirl |
| read/search/fetch/list tools or read-only shell commands | `reading` | debugger scanner |
| apply/edit/write/patch tools or editing shell commands | `coding` | typing |
| shell commands, browser/computer actions, long-running commands | `running` | building crane |
| subagent/thread handoff/task style tools | `delegating` | conducting |
| plan/update-plan style tools | `planning` | wizard |
| `PermissionRequest`, AskUserQuestion, user-choice prompts | `waiting` | alert flash |
| `PreCompact` | `compacting` | sweeping |
| notification/MCP/external-service attention events | `notify` | beacon |
| normal `Stop` | `done` | happy bounce, then idle |
| explicit tool/subagent failure | `error` | confused |
| CLI close watcher or idle sleep timer | `sleep` | sleeping |

## Reference Files

| File | Use it for |
|---|---|
| `references/01-overview-architecture.md` | Buyer-safe architecture overview |
| `references/02-hardware-wiring.md` | Hardware wiring |
| `references/03-firmware-design.md` | Firmware state machine and sprite renderer |
| `references/04-codex-hooks.md` | Codex hook install, trust, testing, mapping |
| `references/05-http-api.md` | WiFi HTTP endpoint contract |
| `references/06-expressions-and-arbitration.md` | 13 sprites and active/resting behavior |
| `references/07-setup-and-flashing.md` | Arduino flash and first-run checklist |

## Important Boundaries

- Do not edit `clawd_mochi/clawd_mochi/clawd_mochi.ino` for Codex adaptation.
- Do not edit any `clawd-mochi-cc` directory when working on CX.
- Keep buyer docs sanitized: use `%USERPROFILE%`, `http://<device-ip>`, and
  `%USERPROFILE%\.codex\hooks\` instead of local developer paths.
- Keep the three transport variants behaviorally aligned; only the sender differs.

Independent maker project inspired by the open-source clawd-tank sprite work
(MIT). Not affiliated with or endorsed by OpenAI or Anthropic.
