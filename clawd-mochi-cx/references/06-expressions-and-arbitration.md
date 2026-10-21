# 06 · Sprite Animations & Arbitration

## The thirteen sprite animations

Each maps 1:1 to a device state (`/event?s=…`). The animation loops continuously
in `loop()` until the next event changes the mood. Every sprite is scaled to a
**uniform on-screen size** (longer side ≈ 210 px) and centered, so all
expressions look equally large regardless of native dimensions.

| State | Sprite | Native W×H | Frames | fps | Background | Visual |
|-------|--------|-----------|--------|-----|------------|--------|
| **idle** | sprite_idle | 72×51 | 96 | 8 | **your** color | gentle floating bob |
| **thinking** | sprite_thinking | 76×92 | 32 | 8 | orange (fixed) | particle swirl upward |
| **reading** | sprite_debugger | 86×43 | 96 | 8 | orange (fixed) | eye-scanner sweep |
| **coding** | sprite_typing | 86×78 | 12 | 8 | orange (fixed) | fingers typing |
| **running** | sprite_building | 124×75 | 8 | 8 | orange (fixed) | crane arm swinging |
| **delegating** | sprite_conducting | 76×78 | 16 | 8 | orange (fixed) | conductor waving (subagents) |
| **planning** | sprite_wizard | 72×129 | 48 | 8 | orange (fixed) | wizard casting a plan |
| **waiting** | sprite_alert | 120×98 | 40 | 8 | orange (fixed) | alert flash |
| **compacting** | sprite_sweeping | 138×56 | 12 | 8 | orange (fixed) | crab sweeping up |
| **notify** | sprite_beacon | 134×127 | 64 | 8 | orange (fixed) | beacon pulse |
| **done** | sprite_happy | 124×89 | 20 | 8 | orange (fixed) | bounce + sparkle, auto-relaxes ~5 s |
| **error** | sprite_confused | 152×113 | 48 | 8 | orange (fixed) | dizzy spiral |
| **sleep** | sprite_sleeping | 92×96 | 36 | 4 | dark (fixed) | slow Zzz drift |

**Design notes:**

- All Codex working states share the **brand orange** background
  (`C_ORANGE = color565(205, 52, 0)` — panel-calibrated for the ST7789's warm-color
  wash) so the device reads as "Codex is busy" at a glance.
- **sleep** uses a dark background (`C_DARKBG`) at half frame rate — visually
  restful to match the "session ended" state.
- **done** is a *moment*, not a resting state — it celebrates for ~5 s, then
  `showManual()` returns the display to your resting choice.
- **Uniform scaling**: `drawSpriteFrame()` scales each sprite (fractional,
  nearest-neighbour) so its longer side ≈ 210 px, capped so neither axis exceeds
  232 px. This is why a wide sprite (running/done/error/notify) looks the same size
  as a narrow one (idle/thinking) — see `references/03`.
- Sprites are centred on the 240×240 display. The transparent key color (`0x18C5`)
  is substituted with the current background color during decode, so sprites
  visually blend into their background.

## The arbitration model (two owners, one screen)

```
                     ┌─────────────────────────────┐
                     │  Is Codex active?      │
                     └──────────────┬──────────────┘
                        yes         │         no
              ┌─────────────────────┘─────────────────────┐
              ▼                                            ▼
   show the matching SPRITE animation          show YOUR resting choice
   on the FIXED brand-orange background        (idle bob / sleeping loop)
   (Codex "owns" the screen)             with YOUR background colour
```

**"Active"** = a working `/event` arrived recently (thinking, reading, coding,
running, delegating, planning, waiting, compacting, notify, error, done).
**"Resting"** = idle event, done auto-relax, 120 s timeout, or boot.

Two state variables capture your manual choice:

```cpp
uint8_t  manualView;   // 0 = idle sprite, 1 = sleeping sprite, 2 = terminal
uint16_t manualBg;     // the background color you picked in the web controller
```

- When you use the web controller, `manualView`/`manualBg` are updated → `MOOD_MANUAL`.
- When a Codex event arrives, the device switches to the matching sprite on
  fixed orange — **your color is preserved separately, not overwritten.**
- When Codex goes idle, `showManual()` restores `manualView` with `manualBg`.

## Self-healing timers

| Timer | Trigger | Effect |
|-------|---------|--------|
| sticky thinking | new `thinking` | hold ~1.1 s before tool states can override |
| done relax | `done` shown | after ~5 s, return to resting |
| activity timeout | working state, no new event for ~120 s | return to resting |

## Resting view → sprite mapping

| `manualView` | Web controller button | Sprite that plays | Loop? |
|--------------|----------------------|-------------------|-------|
| 0 | Normal eyes | sprite_idle | yes |
| 1 | Squish eyes | sprite_sleeping | yes |
| 2 | Codex terminal | text terminal | no sprite |

## Extending the animation set

To add a new animation:

1. Add a `MOOD_*` define, bump `NUM_SPRITES`, and append to each `[NUM_SPRITES]`
   metadata array in the firmware (RLE pointer, offsets, W, H, frame count, fps,
   nudge).
2. Drop the sprite header file into the sketch folder and `#include "sprite_x.h"`.
3. Add a branch in `routeEvent()` (and, if it should self-heal, in the `loop()`
   activity-timeout set).
4. Add a hook in `hooks.json` that sends `/event?s=<newstate>`.

There are more ready-made clawd-tank sprites you can wire up the same way
(`juggling`, `dizzy`, `walking`, `going_away`, `disconnected`, …). Keep working
states on the fixed orange background so the active/resting distinction stays
legible at a glance.

