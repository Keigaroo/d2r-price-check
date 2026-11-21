"""Turns the OCR'd tooltip lines into a structured item."""
import re
from dataclasses import dataclass, field

from .itemdb import ItemDB, fix_ocr, norm

SKIP_PREFIXES = (
    "defense:", "durability:", "required", "one-hand damage", "two-hand damage", "throw damage",
    "chance to block", "item version", "quantity:", "can be inserted", "keep in inventory",
    "right click", "shift +", "shift+", "ctrl +", "ctrl+", "weapons:", "armor:", "helms:",
    "shields:", "kick damage", "smite damage", "sell value", "level requirement",
)
HELP_LINE = re.compile(r"click|hold shift|to compare|attack speed|class -|^- ?fast", re.I)
CLASS_ONLY = re.compile(r"^\((amazon|assassin|barbarian|druid|necromancer|paladin|sorceress|warlock) only\)$", re.I)


@dataclass
class ParsedItem:
    category: str = "unknown"   # unique, set, runeword, misc, rare, crafted, magic, base
    name: str = ""
    base: str = ""
    stats: list = field(default_factory=list)   # remaining text lines (property lines)
    defense: int | None = None
    ethereal: bool = False
    sockets: int | None = None
    unidentified: bool = False
    superior: bool = False
    raw: list = field(default_factory=list)     # (text, colour) for display/debug
    confidence: str = "high"

    @property
    def market_name(self):
        """Name of the Traderie product to look up."""
        if self.category in ("unique", "set", "runeword", "misc"):
            return self.name
        return self.base or self.name

    def headline(self):
        if self.category in ("unique", "set", "rare", "crafted"):
            return f"{self.name}  ({self.base})" if self.base else self.name
        if self.category == "runeword":
            return f"{self.name}  ({self.base})" if self.base else self.name
        return self.name


def _numbers(s):
    return [int(n) for n in re.findall(r"\d+", s)]


def parse(lines, db: ItemDB) -> ParsedItem:
    """lines: list of objects with .text and .color (from ocr.Line), top to bottom."""
    texts = [fix_ocr(norm(l.text)) for l in lines]
    colors = [getattr(l, "color", "unknown") for l in lines]
    item = ParsedItem(raw=list(zip(texts, colors)))
    if not texts:
        item.category = "none"
        return item

    # Pick up flags that can appear anywhere.
    for t in texts:
        lt = re.sub(r"\s+:", ":", re.sub(r"\s+-\s*", "-", t.lower()))
        if lt.startswith("defense:") or lt.startswith("defense "):
            ns = _numbers(t)
            if ns:
                item.defense = ns[0]
        if "ethereal" in lt:
            item.ethereal = True
        m = re.search(r"socketed\s*\((\d)\)", lt)
        if m:
            item.sockets = int(m.group(1))
        if lt == "unidentified" or lt.startswith("unidentified"):
            item.unidentified = True

    first, c1 = texts[0], colors[0]
    second = texts[1] if len(texts) > 1 else ""
    body_start = 1

    misc, ms = db.match_misc(first)
    rw, rws = db.match_runeword(first)
    uq, uqs = db.match_unique(first)
    st, sts = db.match_set(first)
    base2, b2s = db.match_base(second) if second else (None, 0)

    # A runeword tooltip: gold name, grey base, then the rune string like 'JahIthBer'.
    rune_line = any("'" in t and len(t) < 40 and not any(ch.isdigit() for ch in t) for t in texts[1:4])
    candidates = []
    if misc: candidates.append((ms + (4 if c1 in ("orange", "white", "gray") else 0), "misc", misc))
    if rw: candidates.append((rws + (6 if rune_line else 0) + (2 if c1 == "gold" else 0), "runeword", rw))
    if uq: candidates.append((uqs + (4 if c1 == "gold" else 0) - (8 if c1 in ("green", "yellow", "blue") else 0), "unique", uq))
    if st: candidates.append((sts + (6 if c1 == "green" else 0) - (8 if c1 in ("gold", "yellow", "blue") else 0), "set", st))
    candidates.sort(reverse=True)

    if candidates and candidates[0][0] >= 88:
        _, cat, name = candidates[0]
        item.category, item.name = cat, name
        if cat in ("unique", "set", "runeword") and base2:
            item.base = base2
            body_start = 2
        elif cat == "unique":
            item.base = db.uniques[name]["base"]
        elif cat == "set":
            item.base = db.sets[name]["base"]
        if cat == "runeword":
            # Skip the rune-string line.
            while body_start < len(texts) and "'" in texts[body_start] and not any(ch.isdigit() for ch in texts[body_start]):
                body_start += 1
        if max(uqs, sts, rws, ms) < 92:
            item.confidence = "medium"
    elif (base2 and b2s >= 90 and c1 in ("yellow", "orange", "unknown")) or \
            (c1 in ("yellow", "orange") and len(colors) > 1 and colors[1] == c1 and db.match_base(second, 70)[0]):
        base2 = base2 if b2s >= 90 else db.match_base(second, 70)[0]
        # Two-line name with an unrecognised first line -> rare or crafted.
        item.category = "crafted" if c1 == "orange" else "rare"
        item.name, item.base = first, base2
        body_start = 2
    else:
        base_in = db.find_base_inside(first)
        if base_in:
            item.base = base_in
            item.name = first
            lt = first.lower()
            item.superior = lt.startswith("superior")
            if c1 == "blue" or (len(first) > len(base_in) + 3 and not item.superior
                                and not lt.startswith(("ethereal", "low quality", "crude", "cracked", "damaged"))):
                item.category = "magic"
            else:
                item.category = "base"
        else:
            # Name unreadable: work the base out from its damage/defense (gray/white items only).
            looks_like_stat = bool(re.search(r"damage|defense|durability|required", first, re.I))
            fp = None
            if c1 in ("gray", "white", "unknown") or looks_like_stat:
                fp = db.find_base_from_text(texts, item.ethereal, "" if looks_like_stat else first)
            if fp:
                item.category, item.base, item.name = "base", fp, fp
                item.confidence = "medium"
                body_start = 0 if looks_like_stat else 1
            else:
                item.category = "unknown"
                item.name = first
                item.confidence = "low"

    # A gold/green/yellow top line that is only a base name means the real name line above it
    # wasn't read (unique, set, rare names sit above the base). Don't price it as a plain base.
    if item.category in ("base", "magic") and c1 in ("gold", "green", "yellow") and len(texts) > 2:
        item.category = "unknown"
        item.confidence = "low"

    for t in texts[body_start:]:
        lt = re.sub(r"\s+:", ":", re.sub(r"\s+-\s*", "-", t.lower()))
        if not t or lt.startswith(SKIP_PREFIXES) or CLASS_ONLY.match(t) or HELP_LINE.search(t):
            continue
        item.stats.append(t)
    return item
