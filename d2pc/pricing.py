"""Combines trade data into one estimate for the item under the cursor."""
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from rapidfuzz import fuzz

from .traderie import Traderie, TraderieError, listing_price, listing_props, rune_values

RUNE_ORDER = ["Zod", "Cham", "Jah", "Ber", "Sur", "Lo", "Ohm", "Vex", "Gul", "Ist", "Mal", "Um", "Pul", "Lem"]
REF_ITEMS = ["Ber Rune", "Jah Rune", "Ist Rune", "Vex Rune"]

# Traderie product type for each parsed category.
TYPE_PREF = {
    "unique": ["uniques"], "set": ["sets"], "runeword": ["runewords"],
    "misc": ["runes", "gems", "misc", "charms", "keys", "uniques"],
    "rare": ["base", "misc", "charms"], "magic": ["base", "misc", "charms"],
    "crafted": ["base", "misc", "charms"], "base": ["base"],
}


# ---------------------------------------------------------------- stat matching
def _spaced(s):
    s = s.lower()
    s = re.sub(r"\{\{[a-z_]+\}\}", "#", s)
    s = re.sub(r"\d+", "#", s)
    s = re.sub(r"[^a-z#%+\-/ ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _skeleton(s):
    from .itemdb import ocr_key
    return ocr_key(_spaced(s))   # spaces dropped and garbled M's evened out ('D A ITI AGE')


def _likeness(line, template):
    """Best of: exact-order match ignoring spaces, and word-order-free match
    (the game says 'All Resistances +7', Traderie says '+{{value}} to All Resistances')."""
    a = fuzz.ratio(_skeleton(line), _skeleton(template))
    b = fuzz.token_sort_ratio(_spaced(line).replace(" to ", " "), _spaced(template).replace(" to ", " "))
    return max(a, b)


def _value_index(template):
    ph = re.findall(r"\{\{([a-z_]+)\}\}", template)
    return ph.index("value") if "value" in ph else 0


def map_stats(stat_lines, properties):
    """Map OCR'd stat lines onto Traderie property templates. Returns {template: value}."""
    numeric = [p["name"] for p in properties if p.get("type") == "number" and "{{value}}" in (p.get("name") or "")]
    flags = [p["name"] for p in properties if p.get("type") == "bool"
             and p.get("name") not in ("Ladder", "Unidentified", "Ethereal")]
    out = {}
    for line in stat_lines:
        nums = [int(n) for n in re.findall(r"\d+", line)]
        pool = numeric if nums else flags
        best, score = None, 0
        for t in pool:
            sc = _likeness(line, t)
            if sc > score:
                best, score = t, sc
        if not best or score < 86 or best in out:
            continue
        if nums:
            idx = _value_index(best)
            out[best] = nums[idx] if idx < len(nums) else nums[0]
        else:
            out[best] = True
    return out


IGNORED_FOR_SIMILARITY = {"Required Level {{value}}", "Rarity"}


def canon(props):
    """Merge Traderie's duplicate property names and drop ones that don't affect value."""
    out = {}
    for k, v in props.items():
        if k in IGNORED_FOR_SIMILARITY:
            continue
        if k == "+{{value}} Defense":
            k = "Defense"
        out[k] = v
    return out


def item_features(item, properties):
    feats = map_stats(item.stats, properties)
    names = {p.get("name") for p in properties}
    if item.defense is not None and names & {"Defense", "+{{value}} Defense"}:
        feats["Defense"] = item.defense
    if item.sockets:
        sock = f"Socketed ({item.sockets})"
        if sock in names:
            feats[sock] = True
    if item.ethereal and "Ethereal" in names:
        feats["Ethereal"] = True
    if item.unidentified and "Unidentified" in names:
        feats["Unidentified"] = True
    return feats


# How much buyers care about a stat (rough D2 trading consensus). Unlisted stats count 1.
_WEIGHTS = [
    (r"faster cast rate|to all skills|skills\b|all resistances|life stolen|mana stolen|"
     r"to strength|to dexterity|enhanced damage|increased attack speed|faster run|crushing blow|"
     r"deadly strike|socketed|ethereal|to life|faster hit recovery|enhanced defense", 3.0),
    (r"resist \+|to mana$|to mana \(|cannot be frozen|open wounds|requirements", 2.0),
    (r"better chance of getting magic items|to energy|to vitality|^defense$", 1.0),
    (r"damage reduced by|half freeze", 0.7),
    (r"after each kill|minimum damage|maximum damage|replenish life|poison length", 0.5),
    (r"attack rating|extra gold|chance to cast|charges|light radius|stamina|"
     r"minimum (fire|cold|lightning|poison)|maximum (fire|cold|lightning|poison)|poison damage over", 0.3),
]


def stat_weight(name):
    n = name.lower()
    for pat, w in _WEIGHTS:
        if re.search(pat, n):
            return w
    return 1.0


def similarity(mine, theirs):
    """0..1 - how alike two items are, weighted by how much buyers care about each stat.
    A sold item with a valuable stat that mine lacks isn't comparable at all.
    Neutral (0.7) when neither side lists any rolls."""
    keys = {k for k in set(mine) | set(theirs) if not isinstance(mine.get(k, theirs.get(k)), str)}
    if not keys:
        return 0.7
    num = den = 0.0
    for k in keys:
        w = stat_weight(k)
        a, b = mine.get(k), theirs.get(k)
        if isinstance(a, bool) or isinstance(b, bool):
            sc = 1.0 if bool(a) == bool(b) else 0.15
        elif a is None:
            sc = 0.0 if w >= 2 else 0.4     # theirs has a stat mine lacks: theirs is worth more
        elif b is None:
            sc = 0.5 if w >= 2 else 0.6     # mine has an extra stat
        else:
            a, b = float(a), float(b)
            m = max(abs(a), abs(b), 1.0)
            sc = max(0.0, 1 - 2 * abs(a - b) / m)
        num += w * sc
        den += w
    return (num / den) ** 2


def valuable_stats(feats):
    return [k for k in feats if stat_weight(k) >= 2]


# ---------------------------------------------------------------- statistics
def weighted_quantile(pairs, q):
    pairs = sorted(pairs)
    total = sum(w for _, w in pairs)
    if total <= 0:
        return None
    acc = 0.0
    for v, w in pairs:
        acc += w
        if acc >= q * total:
            return v
    return pairs[-1][0]


def _age_days(listing):
    ts = listing.get("updated_at") or listing.get("created_at")
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 86400)
    except Exception:
        return 7.0


def describe_value(v, runes):
    """Express a Traderie value as runes, e.g. 'Vex + Ist' or '2.4 Ist'."""
    if v is None:
        return "?"
    ist = runes.get("Ist Rune")
    order = [(r, runes[r + " Rune"]) for r in RUNE_ORDER if runes.get(r + " Rune")]
    order.sort(key=lambda x: -x[1])
    parts, rest = [], v
    for name, val in order:
        n = int(rest // val)
        if n and len(parts) < 3:
            parts.append(f"{n} {name}" if n > 1 else name)
            rest -= n * val
    combo = " + ".join(parts) if parts and rest < 0.35 * v else None
    in_ist = f"{v / ist:.1f} Ist" if ist else f"{v:.2f} value"
    if combo and in_ist and combo != "Ist":
        return f"{combo}  (~{in_ist})"
    return f"~{in_ist}"


# ---------------------------------------------------------------- main
@dataclass
class Comparable:
    value: float | None
    price_text: str
    weight: float
    age_days: float
    props: dict
    sold: bool


@dataclass
class Estimate:
    ok: bool
    message: str = ""
    product: dict | None = None
    product_url: str = ""
    features: dict = field(default_factory=dict)
    median: float | None = None
    low: float | None = None
    high: float | None = None
    ask_low: float | None = None
    n_sold: int = 0
    n_active: int = 0
    confidence: str = "low"
    comparables: list = field(default_factory=list)
    runes: dict = field(default_factory=dict)


class Pricer:
    def __init__(self, cfg):
        self.cfg = cfg
        self.t = Traderie(cfg)
        self._runes = {}
        self._runes_at = 0

    def reference_runes(self):
        if time.time() - self._runes_at < 3600 and self._runes:
            return self._runes
        batches = []
        for name in REF_ITEMS:
            try:
                it = self.t.find_item(name, ["runes"])
                if it:
                    batches.append(self.t.listings(it["id"], completed=True))
            except TraderieError:
                pass
        vals = rune_values(batches)
        if vals:
            self._runes, self._runes_at = vals, time.time()
        return self._runes

    def estimate(self, item):
        name = item.market_name
        if not name:
            return Estimate(False, "Could not read an item name from the tooltip.")
        try:
            product = self.t.find_item(name, TYPE_PREF.get(item.category))
        except TraderieError as e:
            return Estimate(False, str(e))
        if not product:
            return Estimate(False, f"Traderie has no product called '{name}'.")
        try:
            props = self.t.item_properties(product["id"])
            extra = {}
            if item.category in ("rare", "magic", "crafted", "base"):
                rarity = next((p for p in props if p.get("name") == "Rarity"), None)
                opts = [o.lower() for o in (rarity or {}).get("options") or []]
                # Traderie's Rarity options are e.g. rare / magic / superior / normal.
                want = item.category if item.category in opts else None
                if item.category == "base":
                    want = "superior" if item.superior and "superior" in opts else ("normal" if "normal" in opts else None)
                if want:
                    extra["prop_Rarity"] = want
            sold = self.t.listings(product["id"], completed=True, extra=extra)
            active = self.t.listings(product["id"], completed=False, extra=extra)
        except TraderieError as e:
            return Estimate(False, str(e))

        runes = dict(self.reference_runes())
        runes.update(rune_values([sold, active]))
        feats = item_features(item, props)

        def comps(batch, is_sold):
            out = []
            for L in batch:
                if is_sold and not L.get("completed"):
                    continue
                v, txt = listing_price(L)
                lp = listing_props(L)
                if item.category in ("rare", "magic", "crafted") and lp.get("Rarity") and \
                        str(lp.get("Rarity")).lower() != item.category:
                    continue
                w = similarity(canon(feats), canon(lp))
                age = _age_days(L)
                w *= 0.5 ** (age / 14)  # older trades count less (half weight every 2 weeks)
                out.append(Comparable(v, txt, w, age, lp, is_sold))
            return out

        if item.category in ("rare", "magic", "crafted") and feats and not valuable_stats(feats):
            return Estimate(True, product=product, product_url=self.t.product_url(product), features=feats,
                            runes=runes, confidence="low",
                            message="None of its stats are ones buyers pay for (FCR, resists, skills, leech, "
                                    "Str/Dex, life...). Items like this almost never sell - vendor value.")

        sold_c = comps(sold, True)
        act_c = comps(active, False)
        est = Estimate(True, product=product, product_url=self.t.product_url(product), features=feats, runes=runes)
        # Only trades that genuinely resemble this item may set its price.
        min_w = 0.15 if item.category in ("rare", "magic", "crafted") else 0.05
        priced = [(c.value, c.weight) for c in sold_c if c.value and c.weight >= min_w]
        if not priced and any(c.value for c in sold_c) and item.category in ("rare", "magic", "crafted"):
            est.message = ("No similar items sold recently. Rares/magics whose stats don't match "
                           "anything that sells are usually low value - check the listings to be sure.")
        est.n_sold = len(priced)
        est.n_active = len([c for c in act_c if c.value])
        if priced:
            est.median = weighted_quantile(priced, 0.5)
            est.low = weighted_quantile(priced, 0.25)
            est.high = weighted_quantile(priced, 0.75)
        asks = sorted((c.value for c in act_c if c.value and c.weight >= 0.3))
        if asks:
            est.ask_low = asks[0]
        if est.median is None and asks:
            est.median = asks[len(asks) // 2]
            est.message = "No recent sales found — showing current asking prices instead."

        wsum = sum(w for _, w in priced)
        spread = (est.high - est.low) / est.median if est.median and est.high is not None else 9
        if len(priced) >= 10 and wsum >= 4 and spread < 0.8:
            est.confidence = "high"
        elif len(priced) >= 4 and wsum >= 1.5:
            est.confidence = "medium"
        else:
            est.confidence = "low"
        if item.category in ("rare", "magic", "crafted") and est.confidence == "high":
            est.confidence = "medium"
        if item.confidence == "low":
            est.confidence = "low"

        est.comparables = sorted(sold_c + act_c, key=lambda c: (-c.weight, not c.sold))[:6]
        return est
