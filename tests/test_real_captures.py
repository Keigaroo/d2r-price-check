"""Regression test on real in-game OCR results (1080p, all-caps font), captured 2026-11-20."""
import glob, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import d2pc.ocr as O
from d2pc import main as M
from d2pc.itemdb import ItemDB

EXPECT = {"20261120-183703": ("unique", "Arm of King Leoric"), "20261120-183714": ("rare", "RAVEN CASQUE"), "20261120-183744": ("base", "BLADE"), "20261120-183758": ("base", "Colossus Blade"), "20261120-183813": ("base", "Colossus Blade"), "20261120-183533": ("base", "BLADE"), "20261120-183550": ("base", "BLADE"), "20261120-180755": ("unknown", "RING"), "20261120-181047": ("runeword", "Insight"), "20261120-181102": ("set", "Horazon's Legacy")}
db = ItemDB()
ok = True
for f in sorted(glob.glob(os.path.join(os.path.dirname(__file__), "captures", "*.json"))):
    d = json.load(open(f))
    lines = [O.Line(t, x, y, w, h, c, tuple(rgb)) for t, c, rgb, x, y, w, h in d["all_lines"]]
    CURSOR = {"183533": (546, 860), "183550": (546, 860), "183703": (336, 760), "183714": (478, 380),
              "183744": (546, 860), "183758": (476, 500), "183813": (476, 500)}
    k = os.path.basename(f)[9:15]
    if k in CURSOR:
        cx, cy = CURSOR[k]
    else:
        tl = [l for l in lines if l.text in [t for t, _ in d["tooltip"]]]
        cx = sum(l.cx for l in tl) / len(tl); cy = max(l.bottom for l in tl) + 40
    O.read_lines = lambda img, h, L=lines: L
    _, blk, item = M.analyse_image(None, cx, cy, 1080, db)
    key = os.path.basename(f)[:-5]
    want = EXPECT.get(key, ("unique", "Opalvein"))
    good = (item.category, item.name) == want
    ok &= good
    print("PASS" if good else "FAIL", key, item.category, item.name, "|", item.base, "| stats:", len(item.stats))
print("ALL OK" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
