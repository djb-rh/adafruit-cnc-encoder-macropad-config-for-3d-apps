# Adafruit CNC Encoder Macropad Config for Bambu Studio

CircuitPython firmware that turns Adafruit's [CNC Rotary Macropad](https://learn.adafruit.com/cnc-rotary-macropad) into a dedicated 3D-view navigation controller for [Bambu Studio](https://bambulab.com/en/software/bambu-studio) — pan, rotate, and zoom the build-plate view without touching your mouse.

The macropad enumerates as a USB HID keyboard/mouse composite device and drives Bambu Studio purely through simulated mouse gestures (right-drag to pan, left-drag to rotate, wheel to zoom), so it works regardless of what's selected in the scene and needs no configuration inside Bambu Studio itself.

## Hardware

- [Adafruit Feather RP2040](https://www.adafruit.com/product/4884)
- NeoKey 3x4 ortho snap-apart keyswitches (12 keys, each with an RGB NeoPixel)
- [CNC Rotary Encoder — 100 Pulses per Rotation — 60mm](https://www.adafruit.com/product/5880)

Full build instructions (3D-printed enclosure, wiring, CircuitPython install) are in Adafruit's guide linked above. This repo only covers the `code.py` that runs on it.

## Button layout

```
   1  2  3
   4  5  6
   7  8  9
  10 11 12
```

There are two independent groups of buttons, each lighting up exactly one white LED at a time:

- **Operation** (row 1) — `1` = MOVE&nbsp;&nbsp;`2` = ROTATE&nbsp;&nbsp;`3` = ZOOM
- **Axis** (left column of rows 2–4) — `4` = X&nbsp;&nbsp;`7` = Y&nbsp;&nbsp;`10` = Z

Pressing an operation button (1/2/3) also resets the axis back to X (button 4). Pressing an axis button (4/7/10) only changes which axis the encoder controls — it doesn't change the operation.

Each axis's row also holds two "nudge" buttons that always act on that row's axis, regardless of which axis is currently selected, with their effect depending on the current operation:

| | **MOVE** | **ROTATE** | **ZOOM** |
|---|---|---|---|
| **X** (buttons 5 / 6) | pan left / right | tilt up/down (pitch) | zoom in / out |
| **Y** (buttons 8 / 9) | pan up / down | spin left/right (yaw) | zoom in / out |
| **Z** (buttons 11 / 12) | zoom in / out | spin left/right (yaw) | zoom in / out |

The rotary encoder does the same thing as the currently-selected axis's nudge pair. Panning (MOVE + X or MOVE + Y) is speed-sensitive: spin the encoder fast for big jumps across the plate, spin it slowly for fine positioning.

> Z has no real camera "move" of its own, so MOVE + Z just zooms — the closest equivalent. Bambu Studio's orbit camera also can't roll (rotate around the front-back Y axis), so ROTATE + Y reuses the same left/right spin as ROTATE + Z.

## Installation

1. **Install CircuitPython** on the Feather RP2040, if it isn't already: hold BOOT while plugging in USB, then follow [Adafruit's CircuitPython install guide](https://learn.adafruit.com/adafruit-feather-rp2040-pico/circuitpython) to drag the `.uf2` onto the `RPI-RP2` drive. The board will reboot and mount as a `CIRCUITPY` drive.

2. **Install the required libraries** onto the `CIRCUITPY` drive's `lib` folder. Easiest with [`circup`](https://learn.adafruit.com/keep-your-circuitpython-libraries-on-devices-up-to-date-with-circup):

   ```bash
   pip install circup
   circup install adafruit_hid neopixel adafruit_pixelbuf
   ```

   Or manually copy `adafruit_hid`, `neopixel.mpy`, and `adafruit_pixelbuf.mpy` from the [Adafruit CircuitPython Library Bundle](https://circuitpython.org/libraries) that matches your CircuitPython version into `CIRCUITPY/lib`.

3. **Copy `code.py`** from this repo onto the root of the `CIRCUITPY` drive, replacing whatever is there. CircuitPython auto-reloads and starts running it immediately.

4. **Plug the macropad into the computer running Bambu Studio.** No setup is needed inside Bambu Studio — the device just acts as a mouse. Click into the 3D viewport once so it's focused, then try the buttons.

## Tuning

All of the values worth tweaking live at the top of `code.py`:

| Constant | What it does |
|---|---|
| `PAN_STEP` | Pixels dragged per button tap, and the floor for slow encoder turns |
| `PAN_STEP_MAX` | Pixels dragged per encoder tick at full spin speed |
| `PAN_ACCEL_FAST_DT` / `PAN_ACCEL_SLOW_DT` | How fast (seconds between ticks) you need to spin the encoder to hit max/min pan acceleration |
| `ROTATE_STEP` | Pixels dragged per rotate tick/tap |
| `ZOOM_IN_WHEEL` / `ZOOM_OUT_WHEEL` | Scroll-wheel direction for zoom |

If any direction feels backwards, swap the corresponding function pair in `NUDGE_ACTIONS` / `ENCODER_ACTIONS`, or flip the sign inside the relevant `pan_*`/`pitch_*`/`yaw_*` function.

## Credits

Based on Adafruit's [CNC Rotary Macropad](https://learn.adafruit.com/cnc-rotary-macropad) CircuitPython example by Liz Clark for Adafruit Industries (MIT licensed), adapted here to drive Bambu Studio instead of a general CAD/slicer hotkey set.
