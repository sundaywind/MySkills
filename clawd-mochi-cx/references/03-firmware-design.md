# 03 · Firmware Design

The firmware is a single Arduino sketch (`clawd_mochi.ino`) plus a `rle_sprite.h`
header and 13 sprite data headers, **all bundled in the sketch folder**. Five
concerns, in dependency order:

1. Sprite assets (RLE-compressed headers, self-contained in the sketch folder)
2. WiFi connection (join your network, auto-reconnect)
3. HTTP server (receive `/event` from Codex; serve the web controller)
4. Sprite state machine (which animation is current, which frame)
5. Non-blocking frame loop (advance sprites without blocking HTTP)

Libraries: `Adafruit_GFX`, `Adafruit_ST7789`, `SPI`, `WiFi`, `WebServer`,
`ESPmDNS`, `Preferences`.

---

## 1. Sprite assets

The 13 sprite headers ship **inside the sketch folder** next to
`clawd_mochi.ino` — no copying or external download needed. They are included
with plain relative paths:

```
sprite_idle.h       sprite_thinking.h   sprite_debugger.h
sprite_typing.h     sprite_building.h   sprite_happy.h
sprite_confused.h   sprite_alert.h      sprite_sleeping.h
sprite_conducting.h sprite_wizard.h     sprite_sweeping.h
sprite_beacon.h
```

Each file exposes:
```c
#define {NAME}_WIDTH       <w>
#define {NAME}_HEIGHT      <h>
#define {NAME}_FRAME_COUNT <n>
#define {NAME}_TRANSPARENT_KEY 0x18C5   // dark navy — all sprites use this

static const uint32_t {name}_frame_offsets[n + 1]; // byte offsets into rle_data
static const uint16_t {name}_rle_data[];            // RLE (value, run_count) pairs
```

### Flash budget

| Sprite | W×H | Frames |
|--------|-----|--------|
| idle | 72×51 | 96 |
| thinking | 76×92 | 32 |
| debugger | 86×43 | 96 |
| typing | 86×78 | 12 |
| building | 124×75 | 8 |
| happy | 124×89 | 20 |
| confused | 152×113 | 48 |
| alert | 120×98 | 40 |
| sleeping | 92×96 | 36 |
| conducting | 76×78 | 16 |
| wizard | 72×129 | 48 |
| sweeping | 138×56 | 12 |
| beacon | 134×127 | 64 |

Total sprites ≈ 1 MB. Firmware ≈ 1 MB. Fits in 4 MB flash with the **Huge APP**
partition scheme (see `references/07`).

---

## 2. WiFi (identical to the original version)

NVS config portal, `WiFi.setTxPower(WIFI_POWER_8_5dBm)`, `WiFi.setSleep(false)`,
auto-reconnect watchdog. See `references/03-firmware-design.md` in the original
version for the full explanation — the WiFi layer is **unchanged** in the sprite
edition.

---

## 3. HTTP server (unchanged)

Same routes, same behavior. `/event?s=<state>` is the only endpoint changed —
it now calls `drawSpriteFrame()` instead of old vector functions. Full API: `05`.

---

## 4. Sprite state machine

### Metadata tables

```cpp
#define NUM_SPRITES 13
static const uint16_t *const spriteRLE[NUM_SPRITES] = {
  idle_rle_data,       // MOOD_IDLE       (0)
  thinking_rle_data,   // MOOD_THINKING   (1)
  debugger_rle_data,   // MOOD_READING    (2)
  typing_rle_data,     // MOOD_CODING     (3)
  building_rle_data,   // MOOD_RUNNING    (4)
  happy_rle_data,      // MOOD_DONE       (5)
  confused_rle_data,   // MOOD_ERROR      (6)
  alert_rle_data,      // MOOD_WAITING    (7)
  sleeping_rle_data,   // MOOD_SLEEP      (8)
  conducting_rle_data, // MOOD_DELEGATING (9)
  wizard_rle_data,     // MOOD_PLANNING   (10)
  sweeping_rle_data,   // MOOD_COMPACTING (11)
  beacon_rle_data,     // MOOD_NOTIFY     (12)
};
static const uint32_t *const spriteOffsets[NUM_SPRITES] = { idle_frame_offsets, ... };
static const uint16_t spriteW[NUM_SPRITES]          = { 72, 76, 86, 86,124,124,152,120, 92, 76, 72,138,134};
static const uint16_t spriteH[NUM_SPRITES]          = { 51, 92, 43, 78, 75, 89,113, 98, 96, 78,129, 56,127};
static const uint8_t  spriteFrameCount[NUM_SPRITES] = { 96, 32, 96, 12,  8, 20, 48, 40, 36, 16, 48, 12, 64};
static const uint16_t spriteFpsMs[NUM_SPRITES]      = {125,125,125,125,125,125,125,125,250,125,125,125,125};
//                                                     ~8 fps for all; sleep at ~4 fps
```

### SRAM budget

Largest decode buffer is confused: 152×113×2 = **34,352 bytes** (the new sprites
are all smaller — beacon is 134×127 = 17 KB). ESP32-C3 has ~320 KB SRAM; WiFi
uses ~100–150 KB, leaving ~170 KB free. 34 KB is safe.

```cpp
#define SPRITE_MAX_PIXELS (152 * 113)
static uint16_t spriteBuf[SPRITE_MAX_PIXELS];   // shared decode buffer
```

### `drawSpriteFrame()`

```cpp
void drawSpriteFrame(uint8_t moodId, uint8_t frame, bool fullRedraw) {
  if (moodId >= NUM_SPRITES) return;
  // 1. Look up sprite metadata
  const uint16_t *rle  = spriteRLE[moodId];
  const uint32_t *offs = spriteOffsets[moodId];
  int w = spriteW[moodId], h = spriteH[moodId];
  uint16_t bg = (moodId == MOOD_SLEEP) ? C_DARKBG : animBgColor;

  // 2. RLE decode with inline transparent-key → bg substitution (one pass)
  const uint16_t *src = rle + offs[frame];
  int pos = 0, pixels = w * h;
  while (pos < pixels) {
    uint16_t val = *src++, cnt = *src++;
    uint16_t fill = (val == TRANSPARENT_KEY) ? bg : val;
    while (cnt-- && pos < pixels) spriteBuf[pos++] = fill;
  }

  // 3. Uniform sizing: scale so the longer side ~= 210 px, capped at 232 px
  //    per axis. This makes every sprite look equally large regardless of its
  //    native pixel size (the old integer-only scale left wide sprites tiny).
  const float TARGET = 210.0f;
  float sf = TARGET / (float)max(w, h);
  if (w * sf > 232.0f) sf = 232.0f / w;
  if (h * sf > 232.0f) sf = 232.0f / h;
  int sw = (int)(w * sf + 0.5f), sh = (int)(h * sf + 0.5f);
  int ox = (240 - sw) / 2, oy = (240 - sh) / 2;   // centre on 240×240

  // 4. Background: full clear or 4-strip margin update (anti-flicker)
  if (fullRedraw) {
    tft.fillScreen(bg);
  } else {
    tft.fillRect(0, 0,       240, oy,             bg);  // top
    tft.fillRect(0, oy + sh, 240, 240 - oy - sh,  bg);  // bottom
    tft.fillRect(0, oy,      ox,  sh,             bg);  // left
    tft.fillRect(ox + sw, oy, 240 - ox - sw, sh,  bg);  // right
  }

  // 5. Nearest-neighbour scaled blit (integer ratio maps dest → source pixel)
  static uint16_t rowBuf[240];
  tft.startWrite();
  tft.setAddrWindow(ox, oy, sw, sh);
  for (int dy = 0; dy < sh; dy++) {
    const uint16_t *srcRow = &spriteBuf[((dy * h) / sh) * w];
    for (int dx = 0; dx < sw; dx++) rowBuf[dx] = srcRow[(dx * w) / sw];
    tft.writePixels(rowBuf, sw);
  }
  tft.endWrite();
}
```

**Why uniform scaling?** Native sprite widths range from 72 px (idle) to 152 px
(confused). The earlier integer-only scale (`min(3, 240/w, 240/h)`) forced any
sprite wider than 120 px down to 1× — so running/done/error rendered tiny while
narrow sprites got 2–3×. Fractional nearest-neighbour scaling to a fixed target
makes every expression the same on-screen size. Nearest-neighbour keeps the
crisp pixel-art look.

**Why the 4-strip pattern instead of `fillScreen`?** Clearing the entire 240×240
display (57,600 pixels) every frame at 40 MHz SPI costs most of the frame budget
at 8 fps. The 4 strips clear only the borders around the scaled sprite, leaving
time for the decode + blit. Result: smooth animation with no visible flicker.

### Background colour rules

| State | `animBgColor` | Why |
|-------|--------------|-----|
| Any Codex working state | `C_ORANGE` | Fixed brand orange — set in `routeEvent()` |
| idle / manual resting | `manualBg` | User's web-chosen color — set in `showManual()` |
| MOOD_SLEEP | always `C_DARKBG` | Dark feel for sleeping, overrides animBgColor |

This means your web color picker **cannot bleed into** the Codex expressions.

---

## 5. Non-blocking frame loop

```cpp
void loop() {
  server.handleClient();   // HTTP must run every iteration
  wifiTick();              // reconnect watchdog

  // Self-healing timers:
  if (mood == MOOD_DONE && now - moodTick > 5000) showManual();
  if (working_mood && now - lastEventMs > 120000) showManual();

  // Determine which sprite to animate (mood 0-12 direct;
  // MOOD_MANUAL → idle or sleeping sprite depending on manualView)
  uint8_t animMood = ...;

  if (animMood < NUM_SPRITES && !showingInfo &&
      now - moodTick >= spriteFpsMs[animMood]) {
    moodTick  = now;
    moodFrame = (moodFrame + 1) % spriteFrameCount[animMood];
    drawSpriteFrame(animMood, moodFrame, false);  // false = 4-strip update
  }
}
```

A single sprite animation keeps playing in `loop()` until the next `/event`
changes the mood. No blocking `delay()` calls in the animation path — the HTTP
server remains responsive throughout.

---

## 6. Web controller (unchanged)

The self-contained HTML/JS web controller served from PROGMEM is **identical** to
the original version. The three "views" now map to:

| Button | manualView | Resting sprite |
|--------|-----------|----------------|
| Normal eyes | 0 | idle (bobbing) |
| Squish eyes | 1 | sleeping (closed-eye loops) |
| Codex terminal | 2 | terminal text view (no sprite) |

The background color picker still controls `manualBg`, which becomes the
`animBgColor` for resting sprites.

---

## File layout

Everything the firmware needs lives in one folder — open `clawd_mochi.ino` in
Arduino IDE and compile, no extra setup:

```
clawd_mochi/
└── clawd_mochi/
    ├── clawd_mochi.ino      ← main sketch (HTTP, state machine, loop)
    ├── rle_sprite.h         ← TRANSPARENT_KEY constant + naming doc
    ├── sprite_idle.h        ┐
    ├── sprite_thinking.h    │
    ├── sprite_debugger.h    │
    ├── sprite_typing.h      │
    ├── sprite_building.h    │
    ├── sprite_happy.h       │ 13 sprite headers,
    ├── sprite_confused.h    │ bundled in the sketch
    ├── sprite_alert.h       │ folder (self-contained)
    ├── sprite_sleeping.h    │
    ├── sprite_conducting.h  │
    ├── sprite_wizard.h      │
    ├── sprite_sweeping.h    │
    └── sprite_beacon.h      ┘
```

