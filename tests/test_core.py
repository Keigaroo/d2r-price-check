"""Offline tests: tooltip parsing, stat matching, pricing math (real Traderie samples)."""
import os
import sys
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from d2pc.itemdb import ItemDB
from d2pc.ocr import classify_color
from d2pc.parser import parse
from d2pc import pricing
from d2pc.traderie import listing_price, listing_props

DB = ItemDB()


def L(*rows):
    return [NS(text=t, color=c) for t, c in rows]


RING_PROPS = [{"name": n, "type": "number"} for n in [
    "+{{value}} to Mana", "Poison Resist +{{value}}%", "Damage Reduced by {{value}}", "+{{value}} to Life",
    "+{{value}} to Attack Rating", "Cold Resist +{{value}}%", "Fire Resist +{{value}}%",
    "Lightning Resist +{{value}}%", "+{{value}} to Dexterity", "+{{value}} to Strength",
    "+{{value}} to All Resistances", "{{value}}% Life stolen per hit", "{{value}}% Mana stolen per hit",
    "+{{value}}% Faster Cast Rate", "{{value}}% Better Chance of Getting Magic Items",
    "{{value}}% Chance to cast level {{level}} Charged Bolt when struck", "Required Level {{value}}",
    "+{{value}} to Mana after each Kill",
]] + [{"name": "Rarity", "type": "string", "options": ["rare", "magic", "superior", "normal", "low quality"]}]

SHAKO_PROPS = [{"name": "+{{value}} Defense", "type": "number"}, {"name": "Defense", "type": "number"},
               {"name": "Ethereal", "type": "bool"}, {"name": "Unidentified", "type": "bool"},
               {"name": "+{{value}} to All Skills", "type": "number"}]


def test_unique_with_ocr_typos():
    it = parse(L(("Harlequin Crcst", "gold"), ("Shako", "gold"), ("Defense: 133", "white"),
                 ("Durability: 12 of 12", "white"), ("Required Level: 62", "white"),
                 ("+2 to All Skills", "blue"), ("Physical Damage Received Reduced by 10%", "blue")), DB)
    assert it.category == "unique" and it.name == "Harlequin Crest" and it.base == "Shako", it
    assert it.defense == 133
    assert "+2 to All Skills" in it.stats and not any(s.startswith("Defense") for s in it.stats)


def test_set_item():
    it = parse(L(("Tal Rasha's Guardianship", "green"), ("Lacquered Plate", "green"), ("Defense: 941", "white")), DB)
    assert it.category == "set" and it.name == "Tal Rasha's Guardianship", it


def test_runeword():
    it = parse(L(("Enigma", "gold"), ("Mage Plate", "gray"), ("'JahIthBer'", "gold"), ("Defense: 1102", "white"),
                 ("+2 to All Skills", "blue"), ("+45% Faster Run/Walk", "blue")), DB)
    assert it.category == "runeword" and it.name == "Enigma" and it.base == "Mage Plate", it
    assert it.stats[0] == "+2 to All Skills"


def test_rune():
    it = parse(L(("Ber Rune", "orange"), ("Can be Inserted into Socketed Items", "white"),
                 ("Weapons: 20% Chance of Crushing Blow", "white")), DB)
    assert it.category == "misc" and it.name == "Ber Rune", it


def test_rare_ring():
    it = parse(L(("Dread Loop", "yellow"), ("Ring", "yellow"), ("Required Level: 65", "white"),
                 ("+10% Faster Cast Rate", "blue"), ("+46 to Attack Rating", "blue"),
                 ("Lightning Resist +11%", "blue"), ("+12 to Life", "blue"), ("+83 to Mana", "blue")), DB)
    assert it.category == "rare" and it.base == "Ring", it
    feats = pricing.item_features(it, RING_PROPS)
    assert feats["+{{value}}% Faster Cast Rate"] == 10
    assert feats["+{{value}} to Attack Rating"] == 46
    assert feats["Lightning Resist +{{value}}%"] == 11
    assert feats["+{{value}} to Mana"] == 83 and feats["+{{value}} to Life"] == 12


def test_stat_ocr_noise():
    feats = pricing.map_stats(["+1O% Faster Cast Rote", "5% Life stolen per hlt", "8% Chance to cast level 3 Charged Bolt when struck"], RING_PROPS)
    # '1O' (letter O) is misread; the digits we can read are still matched to the right stat
    assert "+{{value}}% Faster Cast Rate" in feats
    assert feats["{{value}}% Life stolen per hit"] == 5
    assert feats["{{value}}% Chance to cast level {{level}} Charged Bolt when struck"] == 8


def test_magic_and_base():
    m = parse(L(("Jeweler's Monarch of Deflecting", "blue"),), DB)
    assert m.category == "magic" and m.base == "Monarch", m
    b = parse(L(("Monarch", "gray"), ("Defense: 148", "white"), ("Socketed (4)", "white")), DB)
    assert b.category == "base" and b.base == "Monarch" and b.sockets == 4, b
    e = parse(L(("Ethereal Thresher", "gray"), ("Ethereal (Cannot be Repaired), Socketed (4)", "gray")), DB)
    assert e.base == "Thresher" and e.ethereal and e.sockets == 4, e


def test_colors():
    assert classify_color((199, 179, 119)) == "gold"
    assert classify_color((255, 255, 100)) == "yellow"
    assert classify_color((0, 200, 0)) == "green"
    assert classify_color((105, 105, 255)) == "blue"
    assert classify_color((255, 168, 0)) == "orange"
    assert classify_color((230, 230, 230)) == "white"


def test_listing_price_groups():
    # "Ist + Mal  OR  Vex": cheapest complete option is used
    v, txt = listing_price({"prices": [
        {"name": "Ist Rune", "value": 0.16, "quantity": 1, "group": 0},
        {"name": "Mal Rune", "value": 0.1, "quantity": 1, "group": 0},
        {"name": "Vex Rune", "value": 0.5, "quantity": 1, "group": 1}]})
    assert abs(v - 0.26) < 1e-9 and txt == "Ist Rune + Mal Rune"
    # an option containing an item with no value is skipped
    v, _ = listing_price({"prices": [{"name": "Small Charm", "value": None, "quantity": 1, "group": 0},
                                     {"name": "Jah Rune", "value": 3, "quantity": 5, "group": 0}]})
    assert v is None
    assert listing_price({"prices": []})[0] is None


def test_shako_defense_similarity():
    item = parse(L(("Harlequin Crest", "gold"), ("Shako", "gold"), ("Defense: 137", "white")), DB)
    feats = pricing.canon(pricing.item_features(item, SHAKO_PROPS))
    a = listing_props({"properties": [{"name": "+{{value}} Defense", "type": "number", "number": 136}]})
    b = listing_props({"properties": [{"name": "Defense", "type": "number", "number": 99}]})
    c = listing_props({"properties": [{"name": "Ethereal", "type": "bool", "bool": True}]})
    sa, sb, sc = (pricing.similarity(feats, pricing.canon(x)) for x in (a, b, c))
    assert sa > sb > sc, (sa, sb, sc)


def test_describe_value():
    runes = {"Ber Rune": 3.5, "Jah Rune": 3, "Lo Rune": 1.25, "Ohm Rune": 0.75, "Vex Rune": 0.5,
             "Gul Rune": 0.25, "Ist Rune": 0.16, "Mal Rune": 0.1, "Um Rune": 0.06}
    assert pricing.describe_value(0.16, runes).startswith("~1.0 Ist")
    assert pricing.describe_value(0.66, runes).startswith("Vex + Ist")
    assert "Ber" in pricing.describe_value(3.6, runes)


def test_weighted_median_resists_outlier():
    pairs = [(0.16, 1), (0.16, 1), (0.22, 1), (0.5, 1), (75.0, 1)]
    assert pricing.weighted_quantile(pairs, 0.5) == 0.22


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn(); print("PASS", name)
            except Exception as e:
                fails += 1; print("FAIL", name, "->", repr(e))
    sys.exit(1 if fails else 0)
