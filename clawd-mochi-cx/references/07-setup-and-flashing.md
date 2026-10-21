# 07 · Setup & Flashing

End-to-end procedure to go from a bare board to a working animated mascot.

## 1. Toolchain

- **Arduino IDE 2.x** (or arduino-cli).
- **ESP32 board support** — in Preferences → "Additional boards manager URLs" add:
  `https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json`
  then install **"esp32 by Espressif Systems"** from the Boards Manager.
- **Libraries** (Library Manager): `Adafruit GFX Library`, `Adafruit ST7735 and
  ST7789 Library`. (`WiFi`, `WebServer`, `ESPmDNS`, `Preferences` ship with the ESP32 core.)

## 2. Board settings (Tools menu)

| Setting | Value |
|---------|-------|
| Board | **ESP32C3 Dev Module** |
| USB CDC On Boot | **Enabled** ← critical |
| CPU Frequency | 160 MHz |
| Upload Speed | 921600 |
| Port | the COM/tty port for the board |

## 3. Sprite headers — already bundled ← self-contained

All 13 `sprite_*.h` headers and `rle_sprite.h` ship **inside the sketch folder**
next to `clawd_mochi.ino`. There is nothing to copy and no external download —
just open the sketch and compile:

```
clawd_mochi/
└── clawd_mochi/
    ├── clawd_mochi.ino     ← open THIS in Arduino IDE
    ├── rle_sprite.h
    └── sprite_*.h          ← 13 expression headers, already here
```

> Arduino IDE requires the `.ino` to sit in a folder of the **same name**
> (`clawd_mochi/clawd_mochi.ino`). Keep the folder intact when you copy it.

> **Flash size:** the 13 sprite headers add ~1 MB of program data. In Arduino IDE,
> go to Tools → Partition Scheme and select **"Huge APP (3MB No OTA/1MB SPIFFS)"**
> so there's room for firmware + sprites. The default scheme is too small.

## 4. WiFi — configured on the device, not in code

Leave the defaults empty — the device opens a config portal on first boot:

```cpp
const char* STA_SSID = "";   // empty → boot straight into WiFi portal
const char* STA_PASS = "";
```

## 5. Flash

1. Connect the board with a **data-capable** USB cable.
2. Select the right Port in Arduino IDE.
3. Click Upload. Success ends with `Hard resetting via RTS pin...`.

**No COM/serial port appearing?**
- Try a different cable (charge-only won't work).
- Force download mode: hold **BOOT**, tap **RST**, release **BOOT**, upload, then tap **RST** to run.

## 6. First run checklist

1. On first boot the display shows the boot splash + Clawd logo, then the yellow
   **"Set up WiFi"** screen.
2. On a phone, join **`ClaWD-Mochi`** WiFi (password `clawd1234`), open
   `http://[IP]`, tap your 2.4 GHz network, enter the password, **Save**.
3. The device reboots, shows green **"Connected!" + IP** for ~8 s, then fades
   into the sleeping sprite (Zzz animation). Note the IP.
4. Confirm reachability: `curl "http://<that-ip>/state"` → small JSON.
5. Test a sprite: `curl "http://<that-ip>/event?s=coding"` → typing fingers animation.
   Try the new ones too: `delegating`, `planning`, `compacting`, `notify`.
6. Add Codex hooks (`04`) and **restart Codex**.
7. Press Enter in Codex → mascot switches to thinking sprite → done!

## 7. Operating notes

- The device needs only **power** during normal use.
- Keep device and computer on the **same network**.
- On Windows, use the resolve-once IP-cache script (see `04`) to avoid ~10 s
  mDNS stalls with `.local`.

## 8. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Display dark | no power / charge-only cable / loose VCC | data cable, check 3V3 wire |
| Compile error: `sprite_idle.h: No such file` | sketch folder broken up / headers missing | keep `clawd_mochi.ino` and all `sprite_*.h` together in one folder |
| Compile error: not enough flash / program too large | wrong partition scheme | set Tools → Partition Scheme → Huge APP |
| Boot shows "Set up WiFi" | no saved network | normal on first boot; configure via ClaWD-Mochi AP |
| Mascot shows logo then freezes | sprite headers present but mismatched | ensure headers match the `TRANSPARENT_KEY 0x18C5` format |
| Mascot never reacts to Codex | hooks not loaded / wrong IP | `/hooks` in Codex, restart it, check device IP |
| Worked then stopped | hotspot IP changed | device auto-reconnects; if IP changed use `clawd-mochi.local` |
| Events lag ~10 s on Windows | `.local` mDNS blocks | use resolve-once IP cache script from `04` |
| Can't flash | charge-only cable | data cable; or BOOT+RST bootloader mode |
| New board won't join WiFi | C3 antenna/TX-power batch defect | firmware already applies `setTxPower(8.5 dBm)`; ensure 2.4 GHz + ASCII SSID |
| Sprites play but wrong animation for state | cached moodFrame from previous mood | power-cycle; the same-mood guard in `routeEvent` prevents this during normal use |

