# Adafruit CNC Encoder Macropad Config for Bambu Studio

CircuitPython firmware that turns Adafruit's [CNC Rotary Macropad](https://learn.adafruit.com/cnc-rotary-macropad) into a dedicated 3D-view navigation controller — pan, rotate, and zoom without touching your mouse.

It started as a Bambu Studio-only config (hence the repo name), but now supports multiple **profiles** — Bambu Studio and OpenSCAD's render/preview view so far — switchable on the fly from a companion Mac menu bar app, without reflashing the board.

The macropad enumerates as a USB HID keyboard/mouse composite device and drives each program purely through simulated mouse gestures (and the occasional keyboard modifier), so it works regardless of what's selected in the scene and needs no configuration inside the target app itself.

## Hardware

- [Adafruit Feather RP2040](https://www.adafruit.com/product/4884)
- NeoKey 3x4 ortho snap-apart keyswitches (12 keys, each with an RGB NeoPixel)
- [CNC Rotary Encoder — 100 Pulses per Rotation — 60mm](https://www.adafruit.com/product/5880)

Full build instructions (3D-printed enclosure, wiring, CircuitPython install) are in Adafruit's guide linked above. This repo only covers the firmware that runs on it.

## Button layout

```
   1  2  3
   4  5  6
   7  8  9
  10 11 12
```

There are two independent groups of buttons, each lighting up exactly one LED at a time, in the active profile's color:

- **Operation** (row 1) — `1` = MOVE&nbsp;&nbsp;`2` = ROTATE&nbsp;&nbsp;`3` = ZOOM
- **Axis** (left column of rows 2–4) — `4` = X&nbsp;&nbsp;`7` = Y&nbsp;&nbsp;`10` = Z

Pressing an operation button (1/2/3) also resets the axis back to X (button 4). Pressing an axis button (4/7/10) only changes which axis the encoder controls — it doesn't change the operation.

Each axis's row also holds two "nudge" buttons that always act on that row's axis, regardless of which axis is currently selected, with their effect depending on the current operation:

| | **MOVE** | **ROTATE** | **ZOOM** |
|---|---|---|---|
| **X** (buttons 5 / 6) | pan left / right | tilt up/down (pitch) | zoom in / out |
| **Y** (buttons 8 / 9) | pan up / down | spin/roll — profile-dependent, see below | zoom in / out |
| **Z** (buttons 11 / 12) | zoom in / out | spin left/right (yaw) | zoom in / out |

The rotary encoder does the same thing as the currently-selected axis's nudge pair. Panning (MOVE + X or MOVE + Y) is speed-sensitive: spin the encoder fast for big jumps, slowly for fine positioning.

Z has no real camera "move" of its own in either program, so MOVE + Z just zooms in both profiles.

## Profiles

| Profile | Serial name | LED color | ROTATE + Y |
|---|---|---|---|
| Bambu Studio | `bambu` | white | Bambu's orbit camera can't roll, so this reuses the same left/right spin as ROTATE + Z |
| OpenSCAD | `openscad` | cyan | A genuine rotate-around-Y, via Shift + horizontal left-drag (OpenSCAD's nightly build supports independent rotation around all three axes — see `code.py`'s header comment for how this was confirmed against OpenSCAD's own source) |

The active profile is switched over a second USB serial port (`usb_cdc.data`, enabled by `boot.py`, separate from the console/REPL) using a small line-based protocol — see the header comment in `code.py` for the exact commands. In practice you won't hand-write these: the [profile switcher menu bar app](https://github.com/djb-rh/cnc-macropad-profile-switcher) is a small companion Mac app that sends them for you from a dropdown. The board defaults to the `bambu` profile at boot if nothing has told it otherwise.

Adding a new profile means adding its gesture-primitive dict to `PROFILES` in `code.py` (see the existing two for the shape) and redeploying — this repo is still the source of truth for how each program's view actually gets driven, only *which* profile is active is controlled remotely.

## Installation

1. **Install CircuitPython** on the Feather RP2040, if it isn't already: hold BOOT while plugging in USB, then follow [Adafruit's CircuitPython install guide](https://learn.adafruit.com/adafruit-feather-rp2040-pico/circuitpython) to drag the `.uf2` onto the `RPI-RP2` drive. The board will reboot and mount as a `CIRCUITPY` drive.

2. **Install the required libraries** onto the `CIRCUITPY` drive's `lib` folder. Easiest with [`circup`](https://learn.adafruit.com/keep-your-circuitpython-libraries-on-devices-up-to-date-with-circup):

   ```bash
   pip install circup
   circup install adafruit_hid neopixel adafruit_pixelbuf
   ```

   Or manually copy `adafruit_hid`, `neopixel.mpy`, and `adafruit_pixelbuf.mpy` from the [Adafruit CircuitPython Library Bundle](https://circuitpython.org/libraries) that matches your CircuitPython version into `CIRCUITPY/lib`.

3. **Copy `boot.py` and `code.py`** from this repo onto the root of the `CIRCUITPY` drive, replacing whatever is there. `code.py` auto-reloads immediately, but `boot.py` only takes effect after a hard reset — unplug/replug the board, or from the serial console: `import microcontroller; microcontroller.reset()`.

4. **Plug the macropad into the computer running Bambu Studio or OpenSCAD.** No setup is needed inside either app — the device just acts as a mouse (and occasionally a keyboard, for OpenSCAD's Shift-modified rotate). Click into the 3D viewport once so it's focused, then try the buttons.

## Tuning

All of the values worth tweaking live at the top of `code.py`:

| Constant | What it does |
|---|---|
| `PAN_STEP` | Pixels dragged per button tap, and the floor for slow encoder turns |
| `PAN_STEP_MAX` | Pixels dragged per encoder tick at full spin speed |
| `PAN_ACCEL_FAST_DT` / `PAN_ACCEL_SLOW_DT` | How fast (seconds between ticks) you need to spin the encoder to hit max/min pan acceleration |
| `ROTATE_STEP` | Pixels dragged per rotate tick/tap |
| `ZOOM_IN_WHEEL` / `ZOOM_OUT_WHEEL` | Scroll-wheel direction for zoom |

If any direction feels backwards, swap the corresponding function pair in a profile's dict in `PROFILES`, or flip the sign inside the relevant `pan_*`/`pitch_*`/`yaw_*`/`roll_*` function.

## Credits

Based on Adafruit's [CNC Rotary Macropad](https://learn.adafruit.com/cnc-rotary-macropad) CircuitPython example by Liz Clark for Adafruit Industries (MIT licensed), adapted here to drive Bambu Studio and OpenSCAD instead of a general CAD/slicer hotkey set.
