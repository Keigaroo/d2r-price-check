"""Grabs the part of the screen around the mouse cursor where D2R draws the item tooltip.

Works at any resolution: the crop size is a fraction of the monitor height.
"""
import ctypes
import sys

from PIL import Image


def enable_dpi_awareness():
    """Make Windows report real pixel coordinates (needed with display scaling like 125%/150%)."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor aware
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def cursor_pos():
    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    pt = POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def grab_around_cursor():
    """Returns (image, offset_x, offset_y, cursor_x, cursor_y, monitor_dict).

    Coordinates of the returned image are relative to (offset_x, offset_y) on the desktop.
    """
    import mss

    cx, cy = cursor_pos()
    with mss.mss() as sct:
        mon = None
        for m in sct.monitors[1:]:
            if m["left"] <= cx < m["left"] + m["width"] and m["top"] <= cy < m["top"] + m["height"]:
                mon = m
                break
        mon = mon or sct.monitors[1]
        h = mon["height"]
        # D2R tooltips are centred over the item and grow upwards (or downwards near the top),
        # shifting sideways at screen edges. Take the full width of the screen, from the top
        # down to a good way below the cursor, so no tooltip line is ever cut off.
        left = mon["left"]
        right = mon["left"] + mon["width"]
        top = mon["top"]
        bottom = min(mon["top"] + h, cy + int(h * 0.45))
        shot = sct.grab({"left": left, "top": top, "width": right - left, "height": bottom - top})
        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    return img, left, top, cx, cy, mon
