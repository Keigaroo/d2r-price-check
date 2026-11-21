"""Builds d2pc/data/items.json from a blizzhackers/d2data checkout.
Usage: python tools/build_itemdb.py <path-to-d2data/json>
"""
import json, sys, os

src = sys.argv[1]
L = lambda f: json.load(open(os.path.join(src, f), encoding="utf-8"))
S = L("allstrings-eng.json")
txt = lambda k: S.get(k, k)

armor, weapons, misc = L("armor.json"), L("weapons.json"), L("misc.json")
bases = {}
for table in (armor, weapons):
    for code, v in table.items():
        name = txt(v.get("namestr") or code)
        tier = "normal"
        if code == v.get("ubercode"): tier = "exceptional"
        if code == v.get("ultracode"): tier = "elite"
        bases[code] = {"name": name, "tier": tier, "type": v.get("type"),
                       "maxsockets": v.get("gemsockets", 0),
                       # fingerprint used when the name line can't be read
                       "dmg1": [v.get("mindam"), v.get("maxdam")] if v.get("mindam") else None,
                       "dmg2": [v.get("2handmindam"), v.get("2handmaxdam")] if v.get("2handmindam") else None,
                       "def": [v.get("minac"), v.get("maxac")] if v.get("minac") else None,
                       "lvl": v.get("levelreq") or 0}

db = {"uniques": [], "sets": [], "runewords": [], "bases": [], "misc": []}
for v in L("uniqueitems.json").values():
    if not v.get("spawnable") and not v["index"].startswith("PreCrafted"):
        continue
    name = txt(v["index"])
    base = bases.get(v.get("code"), {}).get("name") or txt(v.get("code", ""))
    db["uniques"].append({"name": name, "base": base})
for v in L("setitems.json").values():
    base = bases.get(v.get("item"), {}).get("name") or txt(v.get("item", ""))
    db["sets"].append({"name": txt(v["index"]), "base": base, "set": txt(v.get("set", ""))})
for v in L("runes.json").values():
    if v.get("complete"):
        db["runewords"].append({"name": v["*Rune Name"], "runes": v.get("*RunesUsed", "")})
seen = set()
for b in bases.values():
    if b["name"] in seen: continue
    seen.add(b["name"]); db["bases"].append(b)
for code, v in misc.items():
    n = txt(v.get("namestr") or code)
    if v.get("type") in ("rune", "gem0", "gem1", "gem2", "gem3", "gem4", "gema", "gemr", "geme", "gemt",
                         "gems", "gemd", "gemz", "key", "jewl", "scha", "mcha", "lcha", "amu", "rin",
                         "ques", "upgr") or code.startswith(("pk", "bey", "mbr", "dhn", "tes", "ceh", "bet", "fed", "toa")):
        db["misc"].append({"name": n, "type": v.get("type")})
out = os.path.join(os.path.dirname(__file__), "..", "d2pc", "data", "items.json")
json.dump(db, open(out, "w", encoding="utf-8"), indent=0, ensure_ascii=False)
print({k: len(v) for k, v in db.items()})
