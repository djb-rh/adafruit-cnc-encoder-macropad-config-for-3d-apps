# SPDX-FileCopyrightText: 2024 Liz Clark for Adafruit Industries
# Adapted for multi-profile 3D/2D-view navigation (Bambu Studio, OpenSCAD, QCAD, FreeCAD, ...)
#
# SPDX-License-Identifier: MIT
#
# Physical button numbering:
#   1  2  3
#   4  5  6
#   7  8  9
#  10 11 12
# key_number in this file = button number - 1.
#
# Two independent radio groups, each always has exactly one button lit in
# the active profile's color:
#
#   OPERATION (row 1): 1=MOVE  2=ROTATE  3=ZOOM
#   AXIS      (col 1 of rows 2-4): 4=X  7=Y  10=Z
#
# Pressing an operation button (1/2/3) resets the axis to X (button 4).
# Pressing an axis button (4/7/10) only changes which axis is active; it
# does not change the operation.
#
# Each axis's own row holds its two "nudge" buttons, which always act on
# that axis (regardless of which axis is currently selected) but whose
# effect depends on the current OPERATION:
#   Row 2 (4/5/6):    5/6   = X nudges
#   Row 3 (7/8/9):    8/9   = Y nudges
#   Row 4 (10/11/12): 11/12 = Z nudges
#
# The rotary encoder acts on whichever axis is currently selected (4/7/10),
# using the current operation, exactly like the matching nudge pair would.
# Panning (MOVE + X or Y) is accelerated: spin the encoder fast and each
# tick drags further, spin it slowly for fine control.
#
# --- Profiles ---
# What each button/tick actually *does* (which mouse buttons/keys get
# simulated) depends on the active PROFILE, since different programs bind
# their 3D view differently. The active profile is switched by a Mac-side
# menu bar app over a second USB serial channel (usb_cdc.data, enabled in
# boot.py) so it doesn't interfere with the console/REPL port. Protocol is
# newline-terminated ASCII:
#   Mac -> device: "PROFILE bambu\n" / "PROFILE openscad\n" / "PROFILE qcad\n" / "PROFILE freecad\n" / "QUERY\n"
#   device -> Mac: "OK <profile>\n" / "ERR <reason>\n" / "PROFILE <profile>\n"
# Each profile also gets its own LED color, so the lit buttons alone tell
# you which profile is active without needing to look at the Mac app.
#
#              MOVE                     ROTATE                    ZOOM
#   X    pan left/right (5/6)     tilt up/down -- pitch (5/6)    zoom in/out
#   Y    pan up/down (8/9)        spin/roll, profile-dependent   zoom in/out
#   Z    zoom in/out (11/12)      spin left/right -- yaw (11/12) zoom in/out
#
# Z has no real camera "move" of its own, so MOVE+Z just zooms in every
# profile. ROTATE+Y differs by profile: Bambu Studio's orbit camera can't
# roll, so it reuses yaw (same as ROTATE+Z); OpenSCAD's nightly build can
# genuinely rotate around Y via Shift + horizontal left-drag (verified
# against openscad/openscad's QGLView.cc / MouseConfig.h on GitHub), so its
# profile uses that instead. QCAD is 2D (no rotate at all), so its ROTATE
# operation is just an alias for ZOOM across all three axes -- per the
# QCAD manual's Viewing/Navigating tutorial, panning is normally a held
# middle-mouse-button drag, but on macOS the middle button is commonly
# claimed by Mission Control before QCAD ever sees it (a documented gotcha
# on the QCAD forum), so this profile instead uses the manual's documented
# fallback -- Cmd + left-drag -- which sidesteps that entirely.
#
# FreeCAD's default "CAD" navigation style (per FreeCAD's own docs) also
# offers single-button-plus-modifier alternates to its default chorded
# middle-button gestures: Ctrl + right-drag for pan, Shift + right-drag for
# rotate. Those alternates are used here for the same reason as QCAD --
# avoids relying on a plain middle-click, which macOS commonly intercepts.
# Like Bambu, FreeCAD's CAD-style orbit camera has no independent roll, so
# ROTATE+Y reuses yaw. NOTE: FreeCAD lets users pick a different navigation
# style (Blender, Gesture, Maya-Gesture, ...) -- if these gestures don't
# match, check Edit > Preferences > Display > Navigation and either switch
# to CAD style or let me know which style is active so this can be adjusted.

import time

import board
import keypad
import rotaryio
import neopixel
import usb_cdc
import usb_hid
from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keycode import Keycode
from adafruit_hid.mouse import Mouse

# If any direction feels backwards or too fast/slow, tune these.
ZOOM_IN_WHEEL = 1
ZOOM_OUT_WHEEL = -1
PAN_STEP = 24     # pixels of simulated right-drag for a button tap, and the
                  # slow-turn floor for the encoder (see PAN_STEP_MAX below)
ROTATE_STEP = 24  # pixels of simulated left-drag per encoder detent / button tap

# Pan acceleration: the faster the encoder is spun, the bigger each step's
# drag distance gets, up to PAN_STEP_MAX. Speed is measured as the time
# between consecutive encoder ticks -- shorter gap = faster spin.
PAN_STEP_MAX = 140
PAN_ACCEL_FAST_DT = 0.03  # seconds/tick at or below this -> full PAN_STEP_MAX
PAN_ACCEL_SLOW_DT = 0.25  # seconds/tick at or above this -> plain PAN_STEP

OFF = (0, 0, 0)
WHITE = (255, 255, 255)
CYAN = (0, 255, 255)
ORANGE = (255, 80, 0)
GREEN = (0, 255, 0)

kbd = Keyboard(usb_hid.devices)
mouse = Mouse(usb_hid.devices)

# key matrix: 4 rows x 3 columns = 12 keys, numbered 0-11 top-left to
# bottom-right, matching the physical button-number layout above.
COLUMNS = 3
ROWS = 4
keys = keypad.KeyMatrix(
    row_pins=(board.D12, board.D11, board.D10, board.D9),
    column_pins=(board.A0, board.A1, board.A2),
    columns_to_anodes=False,
)

# neopixels are wired in a serpentine (zigzag) path, so odd rows need
# their column order reversed to get from key_number to physical pixel index
pixels = neopixel.NeoPixel(board.D5, 12, brightness=0.3)


def key_to_pixel_map(key_number):
    row = key_number // COLUMNS
    column = key_number % COLUMNS
    if row % 2 == 1:
        column = COLUMNS - column - 1
    return row * COLUMNS + column


def set_pixel(key_number, color):
    pixels[key_to_pixel_map(key_number)] = color


pixels.fill(OFF)

# radio group: operation select (0-indexed key_number -> operation name)
OPERATION_KEYS = {
    0: "move",    # button 1
    1: "rotate",  # button 2
    2: "zoom",    # button 3
}

# radio group: axis select (0-indexed key_number -> axis name)
AXIS_KEYS = {
    3: "x",  # button 4
    6: "y",  # button 7
    9: "z",  # button 10
}


def drag(button, dx, dy, modifier=None, steps=6, step_delay=0.008):
    """Press `button` (holding `modifier` if given), move (dx, dy) in several
    small steps over ~100ms, release.

    Broken into steps (rather than one instant jump) so the host app sees
    a real drag gesture instead of what looks like a click.
    """
    if modifier is not None:
        kbd.press(modifier)
        time.sleep(0.01)
    mouse.press(button)
    time.sleep(0.02)
    remaining_x, remaining_y = dx, dy
    for i in range(steps, 0, -1):
        step_x = remaining_x // i
        step_y = remaining_y // i
        mouse.move(x=step_x, y=step_y)
        remaining_x -= step_x
        remaining_y -= step_y
        time.sleep(step_delay)
    time.sleep(0.02)
    mouse.release(button)
    if modifier is not None:
        time.sleep(0.01)
        kbd.release(modifier)


def pan_left(distance=PAN_STEP):
    drag(Mouse.RIGHT_BUTTON, -distance, 0)


def pan_right(distance=PAN_STEP):
    drag(Mouse.RIGHT_BUTTON, distance, 0)


def pan_up(distance=PAN_STEP):
    drag(Mouse.RIGHT_BUTTON, 0, -distance)


def pan_down(distance=PAN_STEP):
    drag(Mouse.RIGHT_BUTTON, 0, distance)


# QCAD: Cmd + left-drag pans (avoids the macOS Mission Control middle-click gotcha)
def qcad_pan_left(distance=PAN_STEP):
    drag(Mouse.LEFT_BUTTON, -distance, 0, modifier=Keycode.COMMAND)


def qcad_pan_right(distance=PAN_STEP):
    drag(Mouse.LEFT_BUTTON, distance, 0, modifier=Keycode.COMMAND)


def qcad_pan_up(distance=PAN_STEP):
    drag(Mouse.LEFT_BUTTON, 0, -distance, modifier=Keycode.COMMAND)


def qcad_pan_down(distance=PAN_STEP):
    drag(Mouse.LEFT_BUTTON, 0, distance, modifier=Keycode.COMMAND)


# FreeCAD (CAD navigation style): Ctrl + right-drag pans, avoiding a reliance
# on the style's default plain middle-button drag (same macOS gotcha as QCAD)
def freecad_pan_left(distance=PAN_STEP):
    drag(Mouse.RIGHT_BUTTON, -distance, 0, modifier=Keycode.CONTROL)


def freecad_pan_right(distance=PAN_STEP):
    drag(Mouse.RIGHT_BUTTON, distance, 0, modifier=Keycode.CONTROL)


def freecad_pan_up(distance=PAN_STEP):
    drag(Mouse.RIGHT_BUTTON, 0, -distance, modifier=Keycode.CONTROL)


def freecad_pan_down(distance=PAN_STEP):
    drag(Mouse.RIGHT_BUTTON, 0, distance, modifier=Keycode.CONTROL)


def accelerated_pan_step(dt):
    """Map seconds-since-last-tick to a drag distance: faster spin -> bigger step."""
    if dt <= PAN_ACCEL_FAST_DT:
        return PAN_STEP_MAX
    if dt >= PAN_ACCEL_SLOW_DT:
        return PAN_STEP
    frac = (dt - PAN_ACCEL_FAST_DT) / (PAN_ACCEL_SLOW_DT - PAN_ACCEL_FAST_DT)
    return int(PAN_STEP_MAX - frac * (PAN_STEP_MAX - PAN_STEP))


def zoom_in():
    mouse.move(wheel=ZOOM_IN_WHEEL)


def zoom_out():
    mouse.move(wheel=ZOOM_OUT_WHEEL)


def pitch_neg():  # rotate around X, one direction
    drag(Mouse.LEFT_BUTTON, 0, -ROTATE_STEP)


def pitch_pos():  # rotate around X, other direction
    drag(Mouse.LEFT_BUTTON, 0, ROTATE_STEP)


def yaw_left():  # rotate around Z, one direction
    drag(Mouse.LEFT_BUTTON, -ROTATE_STEP, 0)


def yaw_right():  # rotate around Z, other direction
    drag(Mouse.LEFT_BUTTON, ROTATE_STEP, 0)


def roll_left():  # OpenSCAD only: rotate around Y via Shift + horizontal left-drag
    drag(Mouse.LEFT_BUTTON, -ROTATE_STEP, 0, modifier=Keycode.SHIFT)


def roll_right():  # OpenSCAD only: rotate around Y, other direction
    drag(Mouse.LEFT_BUTTON, ROTATE_STEP, 0, modifier=Keycode.SHIFT)


# FreeCAD (CAD navigation style): Shift + right-drag rotates
def freecad_pitch_neg():  # rotate around X, one direction
    drag(Mouse.RIGHT_BUTTON, 0, -ROTATE_STEP, modifier=Keycode.SHIFT)


def freecad_pitch_pos():  # rotate around X, other direction
    drag(Mouse.RIGHT_BUTTON, 0, ROTATE_STEP, modifier=Keycode.SHIFT)


def freecad_yaw_left():  # rotate around Z, one direction
    drag(Mouse.RIGHT_BUTTON, -ROTATE_STEP, 0, modifier=Keycode.SHIFT)


def freecad_yaw_right():  # rotate around Z, other direction
    drag(Mouse.RIGHT_BUTTON, ROTATE_STEP, 0, modifier=Keycode.SHIFT)


# Each profile supplies the same set of primitives; only *how* they're
# achieved (which mouse button/modifier) differs per program.
PROFILES = {
    "bambu": {
        "pan_left": pan_left, "pan_right": pan_right,
        "pan_up": pan_up, "pan_down": pan_down,
        "zoom_in": zoom_in, "zoom_out": zoom_out,
        "x_rot_neg": pitch_neg, "x_rot_pos": pitch_pos,
        "y_rot_neg": yaw_left, "y_rot_pos": yaw_right,  # no roll available; reuse yaw
        "z_rot_neg": yaw_left, "z_rot_pos": yaw_right,
        "color": WHITE,
    },
    "openscad": {
        "pan_left": pan_left, "pan_right": pan_right,
        "pan_up": pan_up, "pan_down": pan_down,
        "zoom_in": zoom_in, "zoom_out": zoom_out,
        "x_rot_neg": pitch_neg, "x_rot_pos": pitch_pos,
        "y_rot_neg": roll_left, "y_rot_pos": roll_right,  # real rotate-around-Y
        "z_rot_neg": yaw_left, "z_rot_pos": yaw_right,
        "color": CYAN,
    },
    "qcad": {
        "pan_left": qcad_pan_left, "pan_right": qcad_pan_right,
        "pan_up": qcad_pan_up, "pan_down": qcad_pan_down,
        "zoom_in": zoom_in, "zoom_out": zoom_out,
        # 2D CAD has no rotate; ROTATE just doubles up as ZOOM on every axis
        "x_rot_neg": zoom_out, "x_rot_pos": zoom_in,
        "y_rot_neg": zoom_out, "y_rot_pos": zoom_in,
        "z_rot_neg": zoom_out, "z_rot_pos": zoom_in,
        "color": ORANGE,
    },
    "freecad": {
        "pan_left": freecad_pan_left, "pan_right": freecad_pan_right,
        "pan_up": freecad_pan_up, "pan_down": freecad_pan_down,
        "zoom_in": zoom_in, "zoom_out": zoom_out,
        "x_rot_neg": freecad_pitch_neg, "x_rot_pos": freecad_pitch_pos,
        "y_rot_neg": freecad_yaw_left, "y_rot_pos": freecad_yaw_right,  # no roll; reuse yaw
        "z_rot_neg": freecad_yaw_left, "z_rot_pos": freecad_yaw_right,
        "color": GREEN,
    },
}
DEFAULT_PROFILE = "bambu"

# current state
profile = None
current_profile_name = None
operation = None
axis = None


def x_neg():
    if operation == "move":
        profile["pan_left"]()
    elif operation == "rotate":
        profile["x_rot_neg"]()
    elif operation == "zoom":
        profile["zoom_out"]()


def x_pos():
    if operation == "move":
        profile["pan_right"]()
    elif operation == "rotate":
        profile["x_rot_pos"]()
    elif operation == "zoom":
        profile["zoom_in"]()


def y_neg():
    if operation == "move":
        profile["pan_up"]()
    elif operation == "rotate":
        profile["y_rot_neg"]()
    elif operation == "zoom":
        profile["zoom_out"]()


def y_pos():
    if operation == "move":
        profile["pan_down"]()
    elif operation == "rotate":
        profile["y_rot_pos"]()
    elif operation == "zoom":
        profile["zoom_in"]()


def z_neg():
    if operation == "move":
        profile["zoom_out"]()  # closest equivalent to "moving" along Z
    elif operation == "rotate":
        profile["z_rot_neg"]()
    elif operation == "zoom":
        profile["zoom_out"]()


def z_pos():
    if operation == "move":
        profile["zoom_in"]()
    elif operation == "rotate":
        profile["z_rot_pos"]()
    elif operation == "zoom":
        profile["zoom_in"]()


# nudge keys (0-indexed): key_number -> function. Each always acts on its
# own row's axis, regardless of which axis is currently selected.
NUDGE_ACTIONS = {
    4: x_neg,    # button 5
    5: x_pos,    # button 6
    7: y_neg,    # button 8
    8: y_pos,    # button 9
    10: z_neg,   # button 11
    11: z_pos,   # button 12
}

# what the encoder does for each axis, matching the nudge-button behavior
# above. ("move", "x") and ("move", "y") are handled separately in the main
# loop so they can get pan acceleration.
AXIS_POS_NEG = {
    "x": (x_pos, x_neg),
    "y": (y_pos, y_neg),
    "z": (z_pos, z_neg),
}


def activate_axis(key_number):
    global axis
    axis = AXIS_KEYS[key_number]
    for mode_key in AXIS_KEYS:
        set_pixel(mode_key, profile["color"] if mode_key == key_number else OFF)


def activate_operation(key_number):
    global operation
    operation = OPERATION_KEYS[key_number]
    for mode_key in OPERATION_KEYS:
        set_pixel(mode_key, profile["color"] if mode_key == key_number else OFF)
    activate_axis(3)  # pressing an operation button always resets axis to X


def flash(color, times=2, on_time=0.08, off_time=0.06):
    for _ in range(times):
        pixels.fill(color)
        time.sleep(on_time)
        pixels.fill(OFF)
        time.sleep(off_time)


def set_profile(name):
    global profile, current_profile_name
    if name not in PROFILES:
        return False
    profile = PROFILES[name]
    current_profile_name = name
    flash(profile["color"])
    activate_operation(0)  # reset to MOVE + X, redraws LEDs in the new color
    return True


def handle_command(line):
    parts = line.split()
    if not parts:
        return
    cmd = parts[0].upper()
    if cmd == "PROFILE" and len(parts) == 2:
        name = parts[1].lower()
        if set_profile(name):
            data_serial.write("OK {}\n".format(name).encode("utf-8"))
        else:
            data_serial.write("ERR unknown_profile\n".encode("utf-8"))
    elif cmd == "QUERY":
        data_serial.write("PROFILE {}\n".format(current_profile_name).encode("utf-8"))
    else:
        data_serial.write("ERR unknown_command\n".encode("utf-8"))


# start in the default profile, MOVE + X
set_profile(DEFAULT_PROFILE)

encoder = rotaryio.IncrementalEncoder(board.D24, board.D25)
last_position = 0
last_encoder_time = time.monotonic()

# second USB serial port (enabled in boot.py) the Mac-side profile switcher
# talks over; None if boot.py hasn't taken effect yet (needs a hard reset)
data_serial = usb_cdc.data
if data_serial is not None:
    data_serial.timeout = 0  # never block waiting for input
command_buffer = b""

while True:
    key_event = keys.events.get()
    position = encoder.position

    if position != last_position:
        increasing = position > last_position
        now = time.monotonic()
        dt = now - last_encoder_time
        last_encoder_time = now

        if operation == "move" and axis == "x":
            distance = accelerated_pan_step(dt)
            profile["pan_right"](distance) if increasing else profile["pan_left"](distance)
        elif operation == "move" and axis == "y":
            distance = accelerated_pan_step(dt)
            profile["pan_down"](distance) if increasing else profile["pan_up"](distance)
        else:
            pos_action, neg_action = AXIS_POS_NEG[axis]
            pos_action() if increasing else neg_action()
        last_position = position

    if key_event and key_event.pressed:
        key_number = key_event.key_number
        if key_number in OPERATION_KEYS:
            activate_operation(key_number)
        elif key_number in AXIS_KEYS:
            activate_axis(key_number)
        elif key_number in NUDGE_ACTIONS:
            NUDGE_ACTIONS[key_number]()

    if data_serial is not None and data_serial.in_waiting:
        command_buffer += data_serial.read(data_serial.in_waiting)
        while b"\n" in command_buffer:
            line, command_buffer = command_buffer.split(b"\n", 1)
            handle_command(line.decode("utf-8", "ignore").strip())
