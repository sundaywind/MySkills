# 05 · HTTP API Reference

The HTTP API is **identical to the original Clawd Mochi version**. The device
exposes a small HTTP/1.1 GET API on port 80. All responses are tiny JSON. Every
endpoint replies immediately, then performs the draw.

Base URL: `http://<device-ip>/` or `http://clawd-mochi.local/`.

---

## `/event` — the Codex channel

```
GET /event?s=<state>
```

Sets the current sprite animation. This is the only endpoint the hooks use.

| `s=` value | Sprite | Animation |
|------------|--------|-----------|
| `idle` | sprite_idle | gentle floating bob |
| `thinking` | sprite_thinking | particle swirl |
| `reading` | sprite_debugger | eye-scanner sweep |
| `coding` | sprite_typing | fingers typing |
| `running` | sprite_building | crane arm swinging |
| `delegating` | sprite_conducting | conductor waving |
| `planning` | sprite_wizard | wizard casting |
| `waiting` | sprite_alert | alert flash |
| `compacting` | sprite_sweeping | crab sweeping |
| `notify` | sprite_beacon | beacon pulse |
| `done` | sprite_happy | bounce + sparkle (auto-relaxes ~5 s) |
| `error` | sprite_confused | dizzy spiral |
| `sleep` | sprite_sleeping | slow Zzz drift |

Response: `{"ok":1}`.

Example: `curl -s -m 1 "http://clawd-mochi.local/event?s=coding"`

> Unknown or missing `s` is treated as `idle`.

---

## Web controller endpoints (unchanged)

### `/cmd` — pick a manual resting animation
```
GET /cmd?k=<key>
```
| `k=` | Action |
|------|--------|
| `w` | idle sprite (normal resting) |
| `s` | sleeping sprite (squish-eye resting) |
| `d` | Codex terminal view |
| `a` | logo reveal animation |
| `q` | exit terminal view |

### `/redraw` — set background color
```
GET /redraw?bg=<hex>    e.g. bg=%23CD3400
```
Sets `manualBg` and repaints the current resting sprite with the new background.
Does **not** affect Codex's working expressions (those use fixed orange).

### `/char` — type into the on-device terminal
```
GET /char?c=<char>    (%0A=Enter, %08=backspace)
```

### `/speed` — animation speed
```
GET /speed?v=<1|2|3>    1=slow, 2=normal, 3=fast
```
(Multiplies the ms-per-frame values; 3 halves them.)

### `/backlight` — screen on/off
```
GET /backlight?on=<0|1>
```

### Canvas mode
```
GET /canvas?on=<0|1>
GET /draw/clear?bg=<hex>
GET /draw/stroke?pen=<hex>&pts=x,y;x,y;...
```

### `/state` — status JSON
```
GET /state
```
Returns:
```json
{"view":0,"busy":false,"term":false,"bl":true,"speed":1,"sta":true,"ssid":"MyHome"}
```

### `/` — the web controller
```
GET /
```
Serves the self-contained HTML/JS controller when connected, or the WiFi config
portal when in AP mode.

---

## WiFi configuration endpoints (unchanged)

| Endpoint | Action |
|----------|--------|
| `GET /wifi` | Config page (scan → pick → password → Save) |
| `GET /wifi/scan` | JSON list of nearby 2.4 GHz networks |
| `GET /wifi/save?ssid=&pass=` | Save credentials and reboot |
| `GET /wifi/forget` | Clear credentials and reboot into portal |

---

## Conventions

- **Method**: all GET.
- **Encoding**: `#` in colors → `%23`; bare 6-hex also accepted.
- **Errors**: missing required args → `{"e":1}` HTTP 400; unknown route → 404.
- **No auth**: private LAN only. Don't expose to the public internet.

