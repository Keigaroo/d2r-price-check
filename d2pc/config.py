"""Settings, stored in config.json next to the program folder."""
import json
import os
import sys

# Folder for config.json, cache and captures: next to the .exe when packaged, else the project folder.
if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
CACHE_DIR = os.path.join(APP_DIR, "cache")
CAPTURE_DIR = os.path.join(APP_DIR, "captures")

DEFAULTS = {
    # Key combination that triggers a price check while hovering an item.
    "hotkey": "ctrl+d",
    # The result window closes when the mouse moves this far (pixels) away from it,
    # or when you press the hotkey again. (Esc is not used: in D2R it opens the game menu.)
    "close_distance_px": 220,
    # Which market to price against (Traderie property values).
    "platform": "PC",
    "mode": "softcore",
    "ladder": True,
    # Optional: how many d2jsp Forum Gold one Ist rune is worth right now.
    # Leave as null to hide the FG line. Example: 3.5
    "fg_per_ist": None,
    # Save every screenshot + OCR result into the "captures" folder (for troubleshooting).
    "save_captures": True,
    # Keep only this many saved captures.
    "max_saved_captures": 30,
    # Minutes to reuse downloaded trade data before fetching again.
    "listing_cache_minutes": 20,
}


def load():
    cfg = dict(DEFAULTS)
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg.update(json.load(f))
    else:
        save(cfg)
    os.makedirs(CACHE_DIR, exist_ok=True)
    os.makedirs(CAPTURE_DIR, exist_ok=True)
    return cfg


def save(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
