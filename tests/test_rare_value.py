"""Rare-ring pricing against real Traderie completed trades (PC SC Ladder, 2026-11-20)."""
import os, sys
from types import SimpleNamespace as NS
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from d2pc import pricing
from d2pc.itemdb import ItemDB
from d2pc.parser import parse

V = "{{value}}"
AR, FCR, LR, FR, CR, PR = f"+{V} to Attack Rating", f"+{V}% Faster Cast Rate", f"Lightning Resist +{V}%", f"Fire Resist +{V}%", f"Cold Resist +{V}%", f"Poison Resist +{V}%"
ALLR, LL, ML, STR, DEX = f"+{V} to All Resistances", f"{V}% Life stolen per hit", f"{V}% Mana stolen per hit", f"+{V} to Strength", f"+{V} to Dexterity"
LIFE, MANA, GOLD, MF, MAXD = f"+{V} to Life", f"+{V} to Mana", f"{V}% Extra Gold from Monsters", f"{V}% Better Chance of Getting Magic Items", f"+{V} to Maximum Damage"
CB, MAK = f"{V}% Chance to cast level {{{{level}}}} Charged Bolt when struck", f"+{V} to Mana after each Kill"
RUNE = {"Pul": .04, "Lo": 1.25, "Ist": .16, "Sur": 1.75, "Mal": .1, "Ohm": .75, "Jah": 3, "Vex": .5, "Ber": 3.5}
# (price runes, qty), stats  -- a selection of the real sold listings
SOLD = [
 (("Pul", 1), {AR: 82, LIFE: 1, LL: 8, STR: 12, PR: 8}),
 (("Lo", 1), {AR: 74, CB: 10, FCR: 10, ALLR: 10, MANA: 89}),
 (("Ist", 1), {FR: 28, AR: 105, ALLR: 7, LL: 6, STR: 14}),
 (("Sur", 1), {FCR: 10, LIFE: 13, LL: 3, ML: 6, STR: 1, PR: 30}),
 (("Mal", 1), {AR: 105, FCR: 10, ALLR: 10, STR: 4}),
 (("Ohm", 1), {FR: 30, FCR: 10, LL: 8, CR: 29}),
 (("Jah", 1), {AR: 111, LR: 7, FCR: 10, MANA: 32, LL: 8, ML: 5}),
 (("Vex", 1), {FR: 29, FCR: 10, CR: 18, ML: 6}),
 (("Ohm", 1), {AR: 104, LL: 6, CR: 14, ML: 4, STR: 14, PR: 10}),
 (("Jah", 1), {AR: 46, LR: 11, CB: 12, FCR: 10, LIFE: 12, MANA: 83}),
 (("Jah", 2), {LR: 13, MAK: 1, FCR: 10, MANA: 80, LL: 3, MAXD: 4}),
 (("Jah", 2), {FR: 28, GOLD: 29, AR: 74, FCR: 10, LIFE: 35, MANA: 87}),
 (("Lo", 1), {FR: 14, LR: 7, LIFE: 24, CR: 7, ML: 4, STR: 6, PR: 7}),
 (("Jah", 1), {AR: 115, LL: 7, CR: 1, ML: 5, PR: 8}),
 (("Ber", 1), {AR: 87, LR: 25, MAK: 1, FCR: 10, ML: 2, MAXD: 4}),
 (("Jah", 2), {AR: 56, LR: 26, FCR: 10, ML: 4, STR: 15, PR: 7}),
]
PROPS = [{"name": n, "type": "number"} for n in [AR, FCR, LR, FR, CR, PR, ALLR, LL, ML, STR, DEX, LIFE, MANA, GOLD, MF, MAXD, CB, MAK]] \
        + [{"name": "Rarity", "type": "string", "options": ["rare", "magic", "superior", "normal", "low quality"]}]
NOW = datetime.now(timezone.utc).isoformat()

def listings(completed):
    out = []
    for (r, q), st in SOLD:
        props = [{"name": k, "type": "number", "number": v} for k, v in st.items()] + [{"name": "Rarity", "type": "string", "string": "rare"}]
        out.append({"completed": completed, "updated_at": NOW, "properties": props,
                    "prices": [{"name": r + " Rune", "type": "runes", "value": RUNE[r], "quantity": q, "group": 0}]})
    return out

class FakeT:
    def find_item(self, n, p=None): return {"id": "1", "name": "Ring"}
    def item_properties(self, i): return PROPS
    def listings(self, i, completed=True, extra=None): return listings(completed) if completed else []
    def product_url(self, it): return "x"

def price(lines):
    p = pricing.Pricer.__new__(pricing.Pricer)
    p.cfg = {}; p.t = FakeT(); p._runes = {r + " Rune": v for r, v in RUNE.items()}; p._runes_at = 9e18
    item = parse([NS(text=t, color=c) for t, c in lines], ItemDB())
    return p.estimate(item)

junk = price([("ENTROPY GRASP", "yellow"), ("RING", "yellow"), ("REQUIRED LEVEL : 34", "white"),
              ("CHANCE TO CAST LEVEL 5 CHARGED BOLT WHEN STRUCK", "blue"), ("+4 TO m A x 1 mum D A m AGE", "blue"),
              ("+110 TO ATTACK RATING", "blue"), ("31% EXTRA GOLD FROm m ONSTERS", "blue"),
              ("5% BETTER CHANCE OF GETTING m AGIC I TETTIS", "blue")])
print("Entropy Grasp (junk):", junk.median, junk.confidence, "|", junk.message[:60])
assert junk.median is None and "vendor" in junk.message

good = price([("DOOM LOOP", "yellow"), ("RING", "yellow"), ("+10% FASTER CAST RATE", "blue"), ("+90 TO ATTACK RATING", "blue"),
              ("LIGHTNING RESIST +24%", "blue"), ("+80 TO MANA", "blue"), ("6% MANA STOLEN PER HIT", "blue")])
print("FCR/res/mana/ML ring:", pricing.describe_value(good.median, good.runes), good.confidence)
assert good.median >= 1.25

mid = price([("BONE BAND", "yellow"), ("RING", "yellow"), ("+100 TO ATTACK RATING", "blue"), ("6% LIFE STOLEN PER HIT", "blue"),
             ("+12 TO STRENGTH", "blue"), ("FIRE RESIST +20%", "blue")])
print("No-FCR AR/LL/str ring:", pricing.describe_value(mid.median, mid.runes), mid.confidence)
assert mid.median is not None and mid.median < good.median
print("OK")
