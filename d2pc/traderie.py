"""Reads public D2R trade data from Traderie (the same requests its website makes).

No login is used: Traderie returns the 50 most recent listings per query to anonymous visitors.
Results are cached on disk so repeated checks of the same item don't hit the site again.
"""
import hashlib
import json
import os
import time
import urllib.parse

from . import config

BASE = "https://traderie.com/api/diablo2resurrected"
SITE = "https://traderie.com/diablo2resurrected"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
MARKET_PROPS = ("Platform", "Mode", "Ladder", "Game version")


class TraderieError(Exception):
    pass


def _session():
    try:
        from curl_cffi import requests as creq  # looks like real Chrome to Cloudflare
        s = creq.Session(impersonate="chrome")
    except Exception:
        import requests
        s = requests.Session()
        s.headers["User-Agent"] = UA
    s.headers.update({"Accept": "application/json", "Referer": SITE + "/"})
    return s


class Traderie:
    def __init__(self, cfg):
        self.cfg = cfg
        self.s = _session()
        self.cache_dir = os.path.join(config.CACHE_DIR, "traderie")
        os.makedirs(self.cache_dir, exist_ok=True)

    # ---------- low level ----------
    def _get(self, path, params, ttl_seconds):
        url = BASE + path + "?" + urllib.parse.urlencode(params, safe="{}")
        key = hashlib.sha1(url.encode()).hexdigest()
        fp = os.path.join(self.cache_dir, key + ".json")
        if os.path.exists(fp) and time.time() - os.path.getmtime(fp) < ttl_seconds:
            with open(fp, encoding="utf-8") as f:
                return json.load(f)
        try:
            r = self.s.get(url, timeout=15)
        except Exception as e:
            raise TraderieError(f"Could not reach Traderie: {e}")
        if r.status_code != 200:
            snippet = r.text[:200].replace("\n", " ")
            if "Just a moment" in r.text or r.status_code in (403, 503):
                raise TraderieError("Traderie's Cloudflare check blocked the request (HTTP %d)." % r.status_code)
            raise TraderieError(f"Traderie HTTP {r.status_code}: {snippet}")
        data = r.json()
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return data

    # ---------- items ----------
    def find_item(self, name, prefer_types=None):
        """Return Traderie's product record for an exact item name, or None."""
        data = self._get("/items", {"variants": "", "search": name, "tags": "true"}, 7 * 86400)
        items = data.get("items") or []
        exact = [i for i in items if i.get("name", "").lower() == name.lower()]
        pool = exact or items
        if prefer_types:
            pref = [i for i in pool if i.get("type") in prefer_types]
            pool = pref or pool
        return pool[0] if pool and (exact or len(pool) == 1) else (exact[0] if exact else None)

    def item_properties(self, item_id):
        data = self._get("/items", {"id": item_id, "variants": "", "tags": "", "properties": "true",
                                    "adding": "false", "info": "true", "seo": "true"}, 7 * 86400)
        it = (data.get("items") or [data])[0]
        return it.get("properties") or []

    def listings(self, item_id, completed=True, extra=None):
        params = {
            "itemTags": "true", "item": item_id, "selling": "true", "auction": "false",
            "priceValues": "true", "page": 0,
            "prop_Platform": self.cfg["platform"], "prop_Mode": self.cfg["mode"],
            "prop_Ladder": "true" if self.cfg["ladder"] else "false",
        }
        if completed:
            params["completed"] = "true"
        params.update(extra or {})
        ttl = 60 * float(self.cfg.get("listing_cache_minutes", 20))
        data = self._get("/listings", params, ttl)
        return data.get("listings") or []

    def product_url(self, item):
        return f"{SITE}/product/{item['id']}"


def listing_props(listing):
    """{property template: value} for a listing, without the market filters."""
    out = {}
    for p in listing.get("properties") or []:
        name = p.get("name")
        if not name or name in MARKET_PROPS:
            continue
        t = p.get("type")
        if t == "bool":
            out[name] = bool(p.get("bool"))
        elif t == "number":
            out[name] = p.get("number")
        else:
            out[name] = p.get("string") if p.get("string") is not None else p.get("number")
    return out


def listing_price(listing):
    """Value of a listing in Traderie value units, using the cheapest complete price option.

    Sellers often offer alternatives ("Ist + Um OR Vex"): each 'group' is one option.
    Options containing items without a Traderie value are ignored. Returns (value, text) or (None, text).
    """
    groups = {}
    for p in listing.get("prices") or []:
        groups.setdefault(p.get("group", 0), []).append(p)
    best, best_txt = None, ""
    texts = []
    for g, parts in sorted(groups.items()):
        txt = " + ".join(f"{p.get('quantity', 1)}x {p.get('name')}" if p.get("quantity", 1) != 1 else p.get("name", "?")
                         for p in parts)
        texts.append(txt)
        if any(p.get("value") is None for p in parts):
            continue
        total = sum(float(p["value"]) * float(p.get("quantity") or 1) for p in parts)
        if total <= 0:
            continue
        if best is None or total < best:
            best, best_txt = total, txt
    return best, (best_txt or " OR ".join(texts) or "no price listed")


def rune_values(listing_batches):
    """Collect current Traderie values of runes seen in any price."""
    vals = {}
    for batch in listing_batches:
        for L in batch:
            for p in L.get("prices") or []:
                if p.get("type") == "runes" and p.get("value") is not None:
                    vals[p["name"]] = float(p["value"])
    return vals
