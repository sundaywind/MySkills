# 02 · Hardware & Wiring

## Bill of materials

| Part | Spec | Why | ~Cost |
|------|------|-----|-------|
| ESP32-C3 Super Mini | RISC-V MCU, native USB, 2.4 GHz WiFi | brains + WiFi + USB in one tiny board | ~$2.5 |
| ST7789 TFT | 1.54", 240×240, SPI, no touch | the face | ~$3 |
| Jumper wires | 8 × Dupont, 8–10 cm | display ↔ MCU | ~$0.5 |
| 2 × M2×4 mm screws | — | mount the display bezel | ~$0.1 |
| USB-C cable | data-capable (see note) | power + flashing | — |
| 3D-printed case | PLA/PETG, ~30 g | enclosure | ~$0.5 |

**Total: ~$7–8.**

> ⚠️ Use a **data-capable** USB cable, not a charge-only one. A charge-only cable
> powers the board but exposes no serial port, so you can't flash it.

> ⚠️ **ESP32-C3 Super Mini WiFi quirk.** Many boards have an antenna/power-supply
> defect and can't join WiFi at full TX power. The firmware sets
> `WiFi.setTxPower(8.5 dBm)` — keep that line.

## Pin wiring (ST7789 → ESP32-C3)

Hardware SPI is used for speed. Connect **VCC to 3.3 V only — never 5 V.**

| Display pin | ESP32-C3 GPIO | Role | Suggested wire color |
|-------------|---------------|------|----------------------|
| VCC | 3V3 | power (3.3 V) | red |
| GND | GND | ground | black |
| SDA | GPIO 10 | SPI MOSI (data) | orange |
| SCL | GPIO 8 | SPI SCK (clock) | green |
| RES | GPIO 2 | reset | purple |
| DC | GPIO 1 | data/command | blue |
| CS | GPIO 4 | chip select | white |
| BL | GPIO 3 | backlight | yellow |

In firmware:

```cpp
#define TFT_CS  4
#define TFT_DC  1
#define TFT_RST 2
#define TFT_BLK 3   // backlight, driven HIGH/LOW
SPI.begin(8, -1, 10, TFT_CS);  // SCK=8, MOSI=10
tft.init(240, 240);
tft.setSPISpeed(40000000);
tft.setRotation(1);
```

**Why these pins:** GPIO 8 and 10 are the ESP32-C3's hardware SPI pins for
maximum throughput. The sprite renderer pushes ~34 KB of pixel data per frame;
hardware SPI at 40 MHz keeps the animation at ~8 fps without blocking the HTTP
server.

## Power

- USB-C (5 V in, regulated to 3.3 V on-board). Any charger, power bank, or PC port.
- Backlight on GPIO 3 — software controllable via `/backlight?on=0|1`.
- Typical draw: ~50–80 mA (display on, WiFi active, sprite animating).

## Case

- Two-part 3D-printed case (body + back plate) identical to the original Clawd Mochi.
- Print face-down with supports; 0.15–0.20 mm layers, ~15% infill.
- Thread the 8 wires through the back-plate slot, tape the ESP32 inside,
  secure the display with two M2 screws through the bezel holes.

## Assembly order

1. Print and test-fit the case.
2. Wire 8 lines per the table; double-check VCC is on 3V3.
3. Flash firmware + sprite headers (see `07`).
4. Confirm the boot splash and logo animation appear.
5. Tuck boards into case, screw in display, route USB cable, close back.

