# SPDX-License-Identifier: MIT
#
# Enables a second USB CDC serial port (usb_cdc.data) alongside the normal
# console/REPL port, so the Mac-side profile switcher can send commands to
# code.py without interfering with the console. Only takes effect after a
# hard reset (not a code.py hot-reload).

import usb_cdc

usb_cdc.enable(console=True, data=True)
