"""Tooltip grouping on recreated OCR layouts (1080p-ish coordinates)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from d2pc.ocr import Line, tooltip_candidates
from d2pc import main as M
from d2pc.itemdb import ItemDB

def centred(text, cx, y, w, color="blue", h=18, shift=0):
    return Line(text, cx - w / 2 + shift, y, w, h, color)

def opalvein(cx=1180, top=300, mana_shift=14, wide_line=False):
    rows = [("OPALVEIN", 120, "gold"), ("RING", 60, "gold"), ("REQUIRED LEVEL: 50", 230, "white"),
            ("2% CHANCE TO CAST LEVEL 15 FLAME WAVE ON ATTACK", 520, "blue"),
            ("+10% FASTER CAST RATE", 260, "blue"), ("+4% TO MAGIC SKILL DAMAGE", 300, "blue"),
            ("ALL RESISTANCES +7", 220, "blue"), ("+3 LIFE AFTER EACH KILL", 270, "blue"),
            ("TO MANA AFTER EACH KILL", 250, "blue"), ("SHIFT + LEFT CLICK TO UNEQUIP", 330, "white")]
    out = []
    for i, (t, w, c) in enumerate(rows):
        y = top + i * 26
        shift = mana_shift if t.startswith("TO MANA") else 0
        if wide_line and t.startswith("+4%"):
            # OCR glued this line to unrelated text far to the left
            out.append(Line(t, cx - w / 2 - 260, y, w + 260, 18, c))
        else:
            out.append(centred(t, cx, y, w, c, shift=shift))
    return out

def noise():
    return [Line("INVENTORY", 1150, 60, 140, 20, "white"), Line("MANA: 428 / 428", 120, 760, 200, 20, "white"),
            Line("GOLD 120,334", 1300, 900, 150, 18, "white")]

db = ItemDB()
cursor = (1180, 640)
for name, lines in [("plain", opalvein() + noise()),
                    ("dropped +1 shifts centre 30px", opalvein(mana_shift=30) + noise()),
                    ("glued wide line", opalvein(wide_line=True) + noise()),
                    ("both", opalvein(mana_shift=30, wide_line=True) + noise())]:
    M_read = lambda img, h, L=lines: L
    import d2pc.ocr as O
    O.read_lines = M_read
    _, blk, item = M.analyse_image(None, *cursor, 1080, db)
    print(f"{name:32s} -> {item.category:8s} {item.name!r:14} base={item.base!r} stats={len(item.stats)}  first={blk[0].text!r}")
    assert item.category == "unique" and item.name == "Opalvein", name
print("OK")
