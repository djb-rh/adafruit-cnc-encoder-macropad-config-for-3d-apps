# SPDX-FileCopyrightText: 2024 Liz Clark for Adafruit Industries
# Adapted for Bambu Studio 3D-view navigation
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
# Two independent radio groups, each always has exactly one button lit white:
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
#   Row 2 (4/5/6):   5/6   = X nudges
#   Row 3 (7/8/9):   8/9   = Y nudges
#   Row 4 (10/11/12): 11/12 = Z nudges
#
# The rotary encoder acts on whichever axis is currently selected (4/7/10),
# using the current operation, exactly like the matching nudge pair would.
# Panning (MOVE + X or Y) is accelerated: spin the encoder fast and each
# tick drags further (up to PAN_STEP_MAX), spin it slowly for fine control.
#
#              MOVE                      ROTATE                   ZOOM
#   X    pan left/right (5/6)     tilt up/down -- pitch (5/6)   zoom in/out
#   Y    pan up/down (8/9)        spin left/right -- yaw (8/9)  zoom in/out
#   Z    zoom in/out (11/12)      spin left/right -- yaw (11/12) zoom in/out
#
# (Z has no real "move" of its own in a camera view, so MOVE+Z just zooms,
# per user's own call. Y has no real "roll" the camera can do either, since
# Bambu Studio's orbit camera only supports yaw+pitch -- so ROTATE+Y reuses
# the same yaw gesture as ROTATE+Z, per user's choice.)
#
# All navigation is driven by simulated MOUSE gestures, matching Bambu
# Studio's documented 3D-view mouse controls (wiki.bambulab.com):
#   Right-mouse drag = Pan view
#   Left-mouse drag  = Rotate view (horizontal = yaw, vertical = pitch)
#   Mouse wheel      = Zoom view
# Keyboard shortcuts were tried first but turned out to just move the
# selected part instead of panning the camera, so everything here uses
# the mouse instead.

import time

import board
import keypad
import rotaryio
import neopixel
import usb_hid
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

WHITE = (255, 255, 255)
OFF = (0, 0, 0)

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


def drag(button, dx, dy, steps=6, step_delay=0.008):
    """Press `button`, move (dx, dy) in several small steps over ~100ms, release.

    Broken into steps (rather than one instant jump) so the host app sees
    a real drag gesture instead of what looks like a click.
    """
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


def pan_left(distance=PAN_STEP):
    drag(Mouse.RIGHT_BUTTON, -distance, 0)


def pan_right(distance=PAN_STEP):
    drag(Mouse.RIGHT_BUTTON, distance, 0)


def pan_up(distance=PAN_STEP):
    drag(Mouse.RIGHT_BUTTON, 0, -distance)


def pan_down(distance=PAN_STEP):
    drag(Mouse.RIGHT_BUTTON, 0, distance)


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


def yaw_left():  # rotate around Z (or Y, by user's choice), one direction
    drag(Mouse.LEFT_BUTTON, -ROTATE_STEP, 0)


def yaw_right():  # rotate around Z (or Y, by user's choice), other direction
    drag(Mouse.LEFT_BUTTON, ROTATE_STEP, 0)


# current state for the two radio groups
operation = None
axis = None


def x_neg():
    if operation == "move":
        pan_left()
    elif operation == "rotate":
        pitch_neg()
    elif operation == "zoom":
        zoom_out()


def x_pos():
    if operation == "move":
        pan_right()
    elif operation == "rotate":
        pitch_pos()
    elif operation == "zoom":
        zoom_in()


def y_neg():
    if operation == "move":
        pan_up()
    elif operation == "rotate":
        yaw_left()
    elif operation == "zoom":
        zoom_out()


def y_pos():
    if operation == "move":
        pan_down()
    elif operation == "rotate":
        yaw_right()
    elif operation == "zoom":
        zoom_in()


def z_neg():
    if operation == "move":
        zoom_out()  # closest equivalent to "moving" along Z
    elif operation == "rotate":
        yaw_left()
    elif operation == "zoom":
        zoom_out()


def z_pos():
    if operation == "move":
        zoom_in()
    elif operation == "rotate":
        yaw_right()
    elif operation == "zoom":
        zoom_in()


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

# what the encoder does for each (operation, axis) combination, matching
# the nudge-button behavior above. ("move", "x") and ("move", "y") are
# handled separately in the main loop so they can get acceleration.
ENCODER_ACTIONS = {
    ("move", "z"): (zoom_in, zoom_out),
    ("rotate", "x"): (pitch_pos, pitch_neg),
    ("rotate", "y"): (yaw_right, yaw_left),
    ("rotate", "z"): (yaw_right, yaw_left),
    ("zoom", "x"): (zoom_in, zoom_out),
    ("zoom", "y"): (zoom_in, zoom_out),
    ("zoom", "z"): (zoom_in, zoom_out),
}


def activate_axis(key_number):
    global axis
    axis = AXIS_KEYS[key_number]
    for mode_key in AXIS_KEYS:
        set_pixel(mode_key, WHITE if mode_key == key_number else OFF)


def activate_operation(key_number):
    global operation
    operation = OPERATION_KEYS[key_number]
    for mode_key in OPERATION_KEYS:
        set_pixel(mode_key, WHITE if mode_key == key_number else OFF)
    activate_axis(3)  # pressing an operation button always resets axis to X


# start in MOVE + X, matching the default encoder behavior below
activate_operation(0)

encoder = rotaryio.IncrementalEncoder(board.D24, board.D25)
last_position = 0
last_encoder_time = time.monotonic()

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
            pan_right(distance) if increasing else pan_left(distance)
        elif operation == "move" and axis == "y":
            distance = accelerated_pan_step(dt)
            pan_down(distance) if increasing else pan_up(distance)
        else:
            pos_action, neg_action = ENCODER_ACTIONS[(operation, axis)]
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
