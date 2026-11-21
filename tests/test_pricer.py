"""End-to-end pricing with Traderie replaced by real response samples (captured 2026-11-20)."""
import os, sys
from types import SimpleNamespace as NS
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import datetime, timezone
from d2pc import pricing
from d2pc.itemdb import ItemDB
from d2pc.parser import parse
from tests.test_core import RING_PROPS, SHAKO_PROPS

NOW = datetime.now(timezone.utc).isoformat()
def P(*runes):  # ("Ist Rune",0.16,1,0)...
    return [{"name": n, "type": "runes", "value": v, "quantity": q, "group": g} for n, v, q, g in runes]
def num(n, v): return {"name": n, "type": "number", "number": v}
RARE = {"name": "Rarity", "type": "string", "string": "rare"}

SHAKO = [
 (P(("Vex Rune",.5,1,0)), [num("Defense",137)]),
 (P(("Ist Rune",.16,1,0),("Um Rune",.06,1,0)), []),
 (P(("Ist Rune",.16,1,0),("Um Rune",.06,1,0)), [num("+{{value}} Defense",121)]),
 (P(("Gul Rune",.25,1,0)), [num("+{{value}} Defense",103)]),
 (P(("Ist Rune",.16,1,0),("Um Rune",.06,1,0)), [num("Defense",99)]),
 (P(("Ist Rune",.16,1,0)), [num("+{{value}} Defense",113)]),
 (P(("Mal Rune",.1,1,0),("Um Rune",.06,1,0)), [{"name":"Ethereal","type":"bool","bool":True}]),
 (P(("Um Rune",.06,1,0)), [{"name":"Ethereal","type":"bool","bool":True}]),
 (P(("Ist Rune",.16,1,0),("Um Rune",.06,1,0)), [num("+{{value}} Defense",105)]),
 (P(("Ist Rune",.16,1,0),("Mal Rune",.1,1,0),("Vex Rune",.5,1,1)), [num("Defense",131)]),
 (P(("Vex Rune",.5,1,0)), [num("+{{value}} Defense",128)]),
 (P(("Vex Rune",.5,1,0)), [num("+{{value}} Defense",129)]),
 (P(("Ist Rune",.16,1,0)), [num("+{{value}} Defense",104)]),
 (P(("Ist Rune",.16,1,0)), [num("Defense",136)]),
]
RINGS = [
 (P(("Jah Rune",3,1,0)), [num("+{{value}} to Attack Rating",46), num("Lightning Resist +{{value}}%",11), num("+{{value}}% Faster Cast Rate",10), num("+{{value}} to Life",12), num("+{{value}} to Mana",83), RARE]),
 (P(("Jah Rune",3,2,0)), [num("Lightning Resist +{{value}}%",13), num("+{{value}}% Faster Cast Rate",10), num("+{{value}} to Mana",80), num("{{value}}% Life stolen per hit",3), RARE]),
 (P(("Ohm Rune",.75,1,0)), [num("+{{value}} to Attack Rating",104), num("{{value}}% Life stolen per hit",6), num("Cold Resist +{{value}}%",14), num("+{{value}} to Strength",14), RARE]),
 (P(("Sol Rune",.0008,2,0)), [num("Replenish Life +{{value}}",9), num("+{{value}}% Faster Cast Rate",10), num("+{{value}} to Mana",19), RARE]),
 (P(("Jah Rune",3,25,0)), [num("Lightning Resist +{{value}}%",24), num("+{{value}}% Faster Cast Rate",10), num("+{{value}} to Mana",30), num("{{value}}% Life stolen per hit",6), num("{{value}}% Mana stolen per hit",6), RARE]),
 (P(("Ist Rune",.16,1,0)), [num("+{{value}} to Mana",109), {"name":"Rarity","type":"string","string":"magic"}]),
 (P(("Um Rune",.06,1,0),("Pul Rune",.04,1,1)), [num("+{{value}}% Faster Cast Rate",10), num("{{value}}% Life stolen per hit",4), RARE]),
]
def listings(rows, completed=True):
    return [{"completed": completed, "updated_at": NOW, "prices": p, "properties": props} for p, props in rows]

class FakeT:
    def __init__(self, data, props): self.data, self.props = data, props
    def find_item(self, name, prefer=None): return {"id": "1", "name": name}
    def item_properties(self, i): return self.props
    def listings(self, i, completed=True, extra=None): return listings(self.data, completed)
    def product_url(self, it): return "https://traderie.com/x"

def run(data, props, lines):
    p = pricing.Pricer.__new__(pricing.Pricer)
    p.cfg = {}; p.t = FakeT(data, props); p._runes = {"Ist Rune": .16, "Jah Rune": 3, "Ber Rune": 3.5, "Vex Rune": .5, "Um Rune": .06, "Mal Rune": .1, "Ohm Rune": .75, "Gul Rune": .25}; p._runes_at = 9e18
    item = parse([NS(text=t, color=c) for t, c in lines], ItemDB())
    return item, p.estimate(item)

item, est = run(SHAKO, SHAKO_PROPS, [("Harlequin Crest","gold"),("Shako","gold"),("Defense: 136","white")])
print("SHAKO def136:", pricing.describe_value(est.median, est.runes), est.confidence, est.n_sold, "low", est.low, "high", est.high)
item, est2 = run(SHAKO, SHAKO_PROPS, [("Harlequin Crest","gold"),("Shako","gold"),("Defense: 99","white")])
print("SHAKO def99: ", pricing.describe_value(est2.median, est2.runes))
item, est3 = run(SHAKO, SHAKO_PROPS, [("Harlequin Crest","gold"),("Shako","gold"),("Ethereal (Cannot be Repaired)","gray")])
print("SHAKO eth:   ", pricing.describe_value(est3.median, est3.runes))
item, est4 = run(RINGS, RING_PROPS, [("Dread Loop","yellow"),("Ring","yellow"),("+10% Faster Cast Rate","blue"),("+44 to Attack Rating","blue"),("Lightning Resist +12%","blue"),("+15 to Life","blue"),("+80 to Mana","blue")])
print("RARE FCR ring:", pricing.describe_value(est4.median, est4.runes), est4.confidence, [round(c.weight,2) for c in est4.comparables])
item, est5 = run(RINGS, RING_PROPS, [("Bone Band","yellow"),("Ring","yellow"),("+5 to Strength","blue"),("Cold Resist +8%","blue")])
print("RARE junk ring:", est5.median, est5.confidence, est5.message[:50], [round(c.weight,3) for c in est5.comparables])
assert est.median >= est2.median and est3.median < est.median
assert est4.median >= 3 and (est5.median is None or est5.median < 1)
print("OK")
