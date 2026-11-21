# D2R Price Check

**Installing: see `READ ME FIRST.txt` (double-click `Setup.bat` after extracting).**

Hover an item in Diablo II: Resurrected, press **Ctrl+D**, and a small window next to the
cursor shows what similar items actually sold for on Traderie (PC / Softcore / Ladder).

## How it works
1. Takes a screenshot around the mouse (it never reads game memory and never sends input to the game).
2. Reads the tooltip with the text recognition built into Windows, and detects the name colour
   (unique gold, set green, rare yellow, magic blue, crafted orange).
3. Matches the name against the full D2R + Reign of the Warlock item list, and maps each stat line
   to Traderie's stat names.
4. Downloads the 50 most recent *completed* trades plus current listings for that item from Traderie,
   scores each trade by how close its rolls are to yours, and ignores trades that aren't similar.
5. Shows a weighted median price in runes, a typical range, a confidence rating, and the most similar trades.

## Buttons in the result window
- **Traderie** - opens the item's Traderie page.
- **diablo2.io** - copies the item name to the clipboard and opens diablo2.io's price checker
  (paste with Ctrl+V). It isn't queried automatically because the site sits behind a Cloudflare human check.
- **d2jsp** - copies the item name and opens d2jsp's RotW Softcore Ladder trading forum.
  d2jsp's rules forbid automated access, so it is never queried automatically.

## Settings (config.json, created on first run)
| Setting | Meaning |
|---|---|
| hotkey | Price-check key combination. Default `ctrl+d`. |
| platform / mode / ladder | Market to price against. Default `PC` / `softcore` / `true`. |
| fg_per_ist | Optional d2jsp Forum Gold per Ist rune. When set, an FG estimate is shown. |
| close_distance_px | Result window closes when the mouse moves this many pixels away. |
| save_captures | Saves each screenshot + what was read to the `captures` folder. |

## Limits
- Traderie gives anonymous visitors 50 listings per item, so very common items only see the most recent 50 trades.
- Rare/magic estimates compare stats one by one with recent trades of the same base; they are
  never rated higher than MEDIUM confidence.
- Ladder Season 16 started 13 Nov 2026, so ladder prices are still moving quickly.
