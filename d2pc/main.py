"""D2R Price Check — hover an item in Diablo II: Resurrected and press the hotkey (default Ctrl+D).

Run:            python -m d2pc.main
Self-test:      python -m d2pc.main --selftest
Test a picture: python -m d2pc.main --image path\\to\\screenshot.png --cursor 1200,800
"""
import argparse
import json
import os
import queue
import sys
import threading
import time
import traceback

from . import config
from .itemdb import ItemDB
from .parser import parse
from .pricing import Pricer, describe_value


def save_capture(cfg, img, lines, block, item, cursor=None):
    if not cfg.get("save_captures"):
        return
    stamp = time.strftime("%Y%m%d-%H%M%S")
    base = os.path.join(config.CAPTURE_DIR, stamp)
    try:
        img.save(base + ".png")
        with open(base + ".json", "w", encoding="utf-8") as f:
            json.dump({
                "cursor": cursor,
                "all_lines": [(l.text, l.color, l.rgb, round(l.x), round(l.y), round(l.w), round(l.h)) for l in lines],
                "tooltip": [(l.text, l.color) for l in block],
                "parsed": {k: v for k, v in item.__dict__.items()},
            }, f, indent=1, default=str)
        files = sorted(p for p in os.listdir(config.CAPTURE_DIR) if p.endswith(".png"))
        for old in files[: max(0, len(files) - int(cfg.get("max_saved_captures", 30)))]:
            for ext in (".png", ".json"):
                try:
                    os.remove(os.path.join(config.CAPTURE_DIR, old[:-4] + ext))
                except OSError:
                    pass
    except Exception:
        pass


def analyse_image(img, cursor_x, cursor_y, screen_h, db):
    from .ocr import read_lines, tooltip_candidates
    lines = read_lines(img, screen_h)
    cands = tooltip_candidates(lines, cursor_x, cursor_y)
    # Try the nearest few text blocks and keep the first one that names a real item.
    # If a block has no recognisable name, also try it glued to the block right above it.
    strong = ("unique", "set", "runeword", "misc", "rare", "crafted")
    med_h = sorted(l.h for l in lines)[len(lines) // 2] if lines else 15
    # Nearest block first: the first block that is a real item wins, so text elsewhere on the
    # screen (NPC names, stash labels) can never override the item under the mouse.
    # Real tooltips always have several lines; one-line text is a ground-item label (Alt),
    # an NPC name or a panel title, never the item under the mouse.
    cands = [b for b in cands if len(b) >= 2]
    for blk in cands[:4]:
        x0 = min(l.x for l in blk); x1 = max(l.x + l.w for l in blk)
        above = [b for b in cands if b is not blk
                 and 0 <= blk[0].y - max(l.bottom for l in b) <= 3 * med_h          # directly above
                 and min(x1, max(l.x + l.w for l in b)) - max(x0, min(l.x for l in b)) > 0]  # same column
        above.sort(key=lambda b: blk[0].y - max(l.bottom for l in b))
        # Also try without 1-2 leading lines (e.g. a panel title like 'INVENTORY' glued on top).
        options = [o for o in [blk, blk[1:], blk[2:]] + ([above[0] + blk] if above else []) if o]
        parsed = [(o, parse(o, db)) for o in options]
        for o, item in parsed:
            if item.category in strong:
                return lines, o, item
        for o, item in parsed:
            if item.category in ("magic", "base"):
                return lines, o, item
    blk = cands[0] if cands else []
    return lines, blk, parse(blk, db)


def print_result(item, est):
    print("-" * 60)
    print("Item:      ", item.headline(), f"[{item.category}]")
    print("Read lines:", " | ".join(t for t, _ in item.raw))
    if not est.ok:
        print("Error:     ", est.message)
        return
    print("Matched:   ", ", ".join(f"{k}={v}" for k, v in est.features.items()) or "(no rolls)")
    print("Estimate:  ", describe_value(est.median, est.runes), f"[{est.confidence}]",
          f"sales={est.n_sold} active={est.n_active}")
    if est.low is not None:
        print("Range:     ", describe_value(est.low, est.runes), "to", describe_value(est.high, est.runes))
    for c in est.comparables:
        print("   ", "SOLD" if c.sold else "ask ", f"{c.age_days:4.1f}d w={c.weight:.2f}", c.price_text)


def selftest(cfg, db):
    from .parser import ParsedItem
    p = Pricer(cfg)
    ok = True
    for name, cat in [("Harlequin Crest", "unique"), ("Ber Rune", "misc"), ("Enigma", "runeword")]:
        it = ParsedItem(category=cat, name=name, raw=[(name, "")])
        est = p.estimate(it)
        print_result(it, est)
        ok = ok and est.ok and est.median is not None
    try:
        from .ocr import max_dimension
        import winrt.windows.media.ocr  # noqa: F401
        print("-" * 60)
        print("Windows OCR: available (max image size %d px)" % max_dimension())
    except Exception as e:
        ok = False
        print("Windows OCR: NOT available ->", e)
    print("=" * 60)
    print("SELFTEST PASSED" if ok else "SELFTEST FAILED - copy everything above and send it to Claude")


def run_hotkey_app(cfg, db):
    import tkinter as tk

    import keyboard

    from .capture import cursor_pos, grab_around_cursor
    from .overlay import Overlay

    pricer = Pricer(cfg)
    root = tk.Tk()
    root.withdraw()
    ov = Overlay(root, cfg)
    jobs, results = queue.Queue(), queue.Queue()
    busy = threading.Event()

    def worker():
        while True:
            img, ox, oy, cx, cy, mon = jobs.get()
            try:
                lines, block, item = analyse_image(img, cx - ox, cy - oy, mon["height"], db)
                save_capture(cfg, img, lines, block, item, (cx - ox, cy - oy))
                if item.category in ("none", "unknown"):
                    results.put(("error", cx, cy,
                                 "Couldn't find the item's name in the tooltip. Keep the mouse still "
                                 "over the item and press the hotkey again.", item))
                else:
                    est = pricer.estimate(item)
                    print_result(item, est)
                    if est.ok:
                        results.put(("ok", cx, cy, item, est))
                    else:
                        results.put(("error", cx, cy, est.message, item))
            except Exception as e:
                traceback.print_exc()
                results.put(("error", cx, cy, f"Error: {e}", None))
            finally:
                busy.clear()

    threading.Thread(target=worker, daemon=True).start()

    state = {"result_shown": False}

    def on_hotkey():
        if busy.is_set():
            return
        if state["result_shown"]:
            # Second press closes the open result instead of starting a new check.
            state["result_shown"] = False
            results.put(("close",))
            return
        busy.set()
        try:
            shot = grab_around_cursor()   # grab immediately, before the mouse moves
        except Exception as e:
            busy.clear()
            print("Screen capture failed:", e)
            return
        results.put(("busy", shot[3], shot[4]))
        jobs.put(shot)

    def poll():
        try:
            while True:
                r = results.get_nowait()
                if r[0] == "busy":
                    ov.show_busy(r[1], r[2])
                elif r[0] == "ok":
                    ov.show_result(r[1], r[2], r[3], r[4])
                    state["result_shown"] = True
                elif r[0] == "error":
                    ov.show_error(r[1], r[2], r[3], r[4])
                    state["result_shown"] = True
                elif r[0] == "close":
                    ov.close()
                    state["result_shown"] = False
        except queue.Empty:
            pass
        if state["result_shown"] and ov.is_open:
            mx, my = cursor_pos()
            if ov.mouse_far_away(mx, my, cfg.get("close_distance_px", 220)):
                ov.close()
                state["result_shown"] = False
        elif state["result_shown"] and not ov.is_open:
            state["result_shown"] = False
        root.after(50, poll)

    keyboard.add_hotkey(cfg["hotkey"], on_hotkey)
    print(f"D2R Price Check is running. Hover an item in D2R and press {cfg['hotkey'].upper()}.")
    print("The result closes when you move the mouse away or press the hotkey again.")
    print("To quit, close this window.")
    root.after(50, poll)
    root.mainloop()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--image")
    ap.add_argument("--cursor", help="x,y of the cursor inside the image")
    ap.add_argument("--version", action="store_true")
    ap.add_argument("--no-update", action="store_true")
    args = ap.parse_args()

    from .version import __version__
    if args.version:
        print(__version__)
        return

    from .capture import enable_dpi_awareness
    enable_dpi_awareness()
    cfg = config.load()
    db = ItemDB()
    if args.selftest:
        selftest(cfg, db)
        return
    if args.image:
        from PIL import Image
        img = Image.open(args.image).convert("RGB")
        cx, cy = (int(v) for v in args.cursor.split(",")) if args.cursor else (img.width // 2, img.height // 2)
        lines, block, item = analyse_image(img, cx, cy, img.height, db)
        print("Tooltip lines:", [(l.text, l.color, l.rgb) for l in block])
        print_result(item, Pricer(cfg).estimate(item))
        return
    from . import updater
    updater.cleanup_old()
    print(f"D2R Price Check v{__version__}")
    if updater.is_frozen() and not args.no_update:   # zip installs update via update_source
        found = updater.check()
        if found and updater.apply(*found):
            return
    run_hotkey_app(cfg, db)


if __name__ == "__main__":
    sys.exit(main())
