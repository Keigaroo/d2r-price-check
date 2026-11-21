"""Item name database (built from game data) with fuzzy matching for imperfect OCR text."""
import json
import os
import re

from rapidfuzz import fuzz, process

_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "items.json")

# Items that rares/magic items can be, which Traderie lists as their own "base" products.
JEWELRY = ["Ring", "Amulet", "Small Charm", "Large Charm", "Grand Charm", "Jewel"]


def fix_ocr(s: str) -> str:
    """Repair Windows OCR's usual mistakes on D2R's all-capitals font.

    'Ø' for 0, '± I' for +1, '*22%' for +22%, I/l/| next to digits for 1, O next to digits for 0."""
    s = s.replace("\u00d8", "0").replace("\u00f8", "0").replace("\u00b1", "+")
    s = re.sub(r"\*(?=\s*\d)", "+", s)
    s = re.sub(r"\+\s*[Il|](?=[\s%\d]|$)", "+1", s)
    s = re.sub(r"(?<=\d)[Il|]|[Il|](?=\d)", "1", s)
    s = re.sub(r"(?<=\d)[OoQ]|[OoQ](?=\d)", "0", s)
    s = re.sub(r"(?<=[+\-])\s+(?=\d)", "", s)
    return s


def ocr_key(s: str) -> str:
    """Matching key that is blind to how Windows OCR garbles D2R's capital M
    ('ITIESH' / 'rnESH' / 'm ESH' -> 'mesh'). Applied to BOTH sides of a comparison."""
    s = s.lower().replace(" ", "").replace("'", "")
    for bad in ("itie", "iti", "rti", "ttl", "rn", "ff1", "fl1"):
        s = s.replace(bad, "m" if bad not in ("itie",) else "me")
    return s


def norm(s: str) -> str:
    s = s.replace("’", "'").replace("`", "'").replace("—", "-").replace("–", "-")
    s = re.sub(r"\s+", " ", s).strip()
    return s


class ItemDB:
    def __init__(self, path=_DATA):
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        self.uniques = {u["name"]: u for u in d["uniques"]}
        self.sets = {s["name"]: s for s in d["sets"]}
        self.runewords = {r["name"]: r for r in d["runewords"]}
        self.misc = {m["name"]: m for m in d["misc"]}
        self.bases = {b["name"]: b for b in d["bases"]}
        for j in JEWELRY:
            self.bases.setdefault(j, {"name": j, "tier": "", "type": "jewelry", "maxsockets": 0})
        # Longest first so "Grand Charm" wins over "Charm", "Archon Plate" over "Plate".
        self.base_names_by_len = sorted(self.bases, key=len, reverse=True)

    @staticmethod
    def _best(text, choices, cutoff):
        if not text or not choices:
            return None, 0
        # OCR of D2R's capitals often splits words ('OPAL VEIN', 'O P ALVEI N'): compare without spaces.
        m = process.extractOne(norm(text), list(choices), scorer=fuzz.ratio,
                               processor=ocr_key, score_cutoff=cutoff)
        return (m[0], m[1]) if m else (None, 0)

    def match_unique(self, t, cutoff=84): return self._best(t, self.uniques, cutoff)
    def match_set(self, t, cutoff=84): return self._best(t, self.sets, cutoff)
    def match_runeword(self, t, cutoff=84): return self._best(t, self.runewords, cutoff)
    def match_misc(self, t, cutoff=86): return self._best(t, self.misc, cutoff)
    def match_base(self, t, cutoff=84): return self._best(t, self.bases, cutoff)

    def find_base_inside(self, text):
        """For magic/normal items whose single name line contains the base, e.g.
        'Cruel Colossus Blade of Quickness' -> 'Colossus Blade'."""
        t = norm(text).lower()
        for name in self.base_names_by_len:
            if re.search(r"\b" + re.escape(name.lower()) + r"\b", t):
                return name
        # Fuzzy fallback for OCR mistakes (only for text long enough to mean something).
        best, score = None, 0
        if len(t.replace(" ", "")) < 4:
            return None
        for name in self.base_names_by_len:
            if len(name) < 4 or len(t) < 0.6 * len(name):
                continue
            s = fuzz.partial_ratio(name.lower(), t)
            if s > score or (s == score and best and len(name) > len(best)):
                best, score = name, s
        return best if score >= 90 else None

    def find_base_from_text(self, texts, ethereal=False, name_hint=""):
        return self.base_from_fingerprint(texts, ethereal, name_hint)

    def base_from_fingerprint(self, texts, ethereal=False, name_hint=""):
        """Identify a weapon/armor base from its damage or defense numbers when the name line
        is missing or unreadable. Returns a base name or None."""
        one = two = None
        defense = None
        for t in texts:
            lt = t.lower().replace(" ", "")
            m = re.search(r"one-?hand.*?(\d+)to(\d+)", lt)
            if m: one = (int(m.group(1)), int(m.group(2)))
            m = re.search(r"two-?hand.*?(\d+)to(\d+)", lt)
            if m: two = (int(m.group(1)), int(m.group(2)))
            m = re.match(r"defense:?(\d+)", lt)
            if m: defense = int(m.group(1))
        factors = (1.5,) if ethereal else (1.0,)
        hint = re.sub(r"[^a-z]", "", (name_hint or "").lower())
        best, best_score = None, -1e9
        for b in self.bases.values():
            score = None
            for f in factors:
                errs = []
                for got, have in ((one, b.get("dmg1")), (two, b.get("dmg2"))):
                    if got is None:
                        continue
                    if not have:
                        errs = None
                        break
                    lo, hi = int(have[0] * f), int(have[1] * f)
                    # allow up to +15% from 'Superior' enhanced damage
                    e = 0
                    for g, base in ((got[0], lo), (got[1], hi)):
                        if g < base - 1 or g > base * 1.16 + 1:
                            e += 100
                        else:
                            e += abs(g - base) * 0.2
                    errs.append(e)
                if errs is None:
                    continue
                if errs:
                    score = -sum(errs)
                elif defense is not None and b.get("def"):
                    lo, hi = b["def"][0] * f, b["def"][1] * f * 1.16 + 1
                    score = 0 if lo - 1 <= defense <= hi else -100
            if score is None:
                continue
            if hint:
                score += fuzz.ratio(hint, b["name"].lower().replace(" ", "")) / 10
            if score > best_score:
                best, best_score = b["name"], score
        # weapons: must fit the damage; armor: defense fits and the garbled name resembles it
        if best is None or best_score < -50:
            return None
        if one is None and two is None and best_score < 4:
            return None
        return best
