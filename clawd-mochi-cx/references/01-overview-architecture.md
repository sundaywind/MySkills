# 01 · Overview & Architecture

## The idea

A coding session has rhythm: you think, Codex reads your code, writes a patch,
runs the tests, spawns a subagent, asks you a question, finishes. **Clawd Mochi
CX** turns that invisible rhythm into a physical, glanceable desk companion. The
mascot plays a different pixel-art animation for each Codex state —
**thirteen** animations in all.

## System diagram

```
            COMPUTER (running Codex)                 DEVICE (Clawd Mochi)
 ┌──────────────────────────────────────────┐     ┌──────────────────────────────┐
 │  Codex                              │     │  ESP32-C3 Super Mini         │
 │   │                                       │     │   • WiFi STA (joins your LAN)│
 │   │ fires hooks on every event            │     │   • HTTP server  :80         │
 │   ▼                                       │     │   • sprite state machine     │
 │  hooks.json hooks ── curl ───────────────────►  /event?s=<state>           │
 │   (SessionStart, UserPromptSubmit,        │ WiFi│   • RLE sprite decoder       │
 │    PreToolUse/PostToolUse, PreCompact,    │     │        │                     │
 │    PermissionRequest, Notification, Stop) │     │        ▼                     │
 │                                           │     │   ST7789 240×240 display     │
 └──────────────────────────────────────────┘     └──────────────────────────────┘
        ▲                                                   ▲
        │ you type, approve permissions                     │ phone/browser web
        │                                                   │ controller (manual)
```

Two independent inputs feed one screen:

1. **Codex** (automatic) — pushes a state on every activity.
2. **You** (manual) — pick a resting animation + background color from the web
   controller the device serves.

An **arbitration rule** decides which wins (see `06`).

## Data flow, end to end

1. You press Enter → `UserPromptSubmit` → `…/event?s=thinking` → thinking sprite starts.
2. Codex reads, searches, fetches, lists, or runs a read-only command → `reading` → debugger-scan animation.
3. Codex applies a patch, edits, writes, or runs a file-changing command → `coding` → typing fingers animation.
4. Codex runs shell/browser/computer work or a long command → `running` → crane/building animation.
5. Codex starts a subagent or thread handoff → `delegating` → conductor animation.
6. Codex updates or presents a plan → `planning` → wizard animation.
7. Codex needs your approval or a choice → `PermissionRequest` / user-input tool → `waiting` → alert-flash animation.
8. Codex compacts context → `PreCompact` → `compacting` → sweeping animation.
9. Codex emits a notification or external-service attention event → `notify` → beacon pulse.
10. Codex finishes normally → `Stop` → `done` → happy bounce, auto-relaxes after ~5 s.
11. A tool or subagent explicitly fails → `error` → confused animation.
12. You leave it idle or close a CLI session → idle timer / close watcher → `sleep` → slow sleeping Zzz.

## Design principles

- **Never block the human's tool.** Hook `curl`s use `-m 1`. If the mascot is off,
  the hook fails in ≤1 s and Codex is unaffected.

- **Push, don't poll.** The PC pushes state on each event. The device never
  polls the PC.

- **Discrete events, continuous animation.** One `/event` starts a looping sprite;
  `loop()` advances frames until the next event. The mascot looks alive between events.

- **Tolerate missing/late events.** "done" auto-relaxes; working states time out
  after 120 s; "thinking" is held a minimum time so it's always visible.

- **Waiting vs. working is a first-class distinction.** `PermissionRequest` +
  `PostToolUse` correct the sprite from "working" to "waiting" during a permission
  prompt, then back to "working" after approval.

- **Two owners, clear priority.** Codex owns the screen while active (fixed
  orange look). Your manual web selection owns the rest of the time.

## Sprite source

All 13 sprite animation headers (`.h` files) ship **inside the sketch folder**
next to `clawd_mochi.ino`, so the firmware compiles with no external downloads.
They are RLE-compressed RGB565 C arrays; the artwork derives from the open-source
[clawd-tank](https://github.com/marciogranzotto/clawd-tank) project (MIT). The
firmware's `drawSpriteFrame()` decodes them frame-by-frame into a shared SRAM
buffer and scales each to a uniform on-screen size.

## Bill of complexity

| Layer | Size (approx) | Notes |
|-------|----------------|-------|
| Hardware | — | 8 wires |
| Sprite headers | ~1 MB flash | 13 `.h` files, bundled in the sketch folder |
| Firmware | ~1,500 C++ | single `.ino`, no external state |
| Hooks | ~1 JSON file | declarative `curl` commands |
| Web controller | embedded HTML/JS | served from PROGMEM by the device |

