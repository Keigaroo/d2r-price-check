"""The small always-on-top result window shown next to the cursor."""
import ctypes
import re
import sys
import tkinter as tk
import webbrowser

from .pricing import describe_value

BG = "#0d0d0f"
FG = "#d8d8d8"
DIM = "#8a8a8a"
COLORS = {"unique": "#c7b377", "set": "#00d000", "runeword": "#c7b377", "rare": "#ffff64",
          "magic": "#6969ff", "crafted": "#ffa800", "misc": "#ffa800", "base": "#d8d8d8",
          "unknown": "#d8d8d8"}
CONF_COLORS = {"high": "#4caf50", "medium": "#e0b030", "low": "#e05050"}
D2IO_URL = "https://diablo2.io/price-check/"
D2JSP_URL = "https://forums.d2jsp.org/forum.php?f=271"


def stat_text(k, v):
    """'+{{value}}% Faster Cast Rate', 10 -> '+10% Faster Cast Rate'. Other placeholders
    Traderie doesn't record (skill level, charges) are dropped."""
    if isinstance(v, bool):
        return k
    s = k.replace("{{value}}", str(v))
    s = re.sub(r"level \{\{level\}\} ", "", s)
    s = re.sub(r"\s*\(\{\{charges\}\}/\{\{charges\}\} Charges\)", "", s)
    return re.sub(r"\{\{[a-z_]+\}\}", "#", s)


def _no_activate(win):
    """Keep the game focused: the window shows on top but never takes keyboard focus."""
    if sys.platform != "win32":
        return
    try:
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        GWL_EXSTYLE, WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW, WS_EX_TOPMOST = -20, 0x08000000, 0x80, 0x8
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                                            style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST)
    except Exception:
        pass


class Overlay:
    def __init__(self, root, cfg):
        self.root = root
        self.cfg = cfg
        self.win = None

    def close(self):
        if self.win is not None:
            try:
                self.win.destroy()
            except Exception:
                pass
            self.win = None

    def _new(self, x, y):
        self.close()
        w = tk.Toplevel(self.root)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.configure(bg=BG, highlightthickness=1, highlightbackground="#5a4a2a")
        self.win = w
        self._anchor = (x, y)
        return w

    def _place(self):
        w = self.win
        w.update_idletasks()
        x, y = self._anchor
        sw, sh = w.winfo_screenwidth(), w.winfo_screenheight()
        ww, wh = w.winfo_reqwidth(), w.winfo_reqheight()
        nx = min(max(0, x + 24), sw - ww)
        ny = min(max(0, y - wh // 2), sh - wh)
        w.geometry(f"+{nx}+{ny}")
        _no_activate(w)

    def _label(self, parent, text, fg=FG, size=10, bold=False, wrap=420):
        lb = tk.Label(parent, text=text, fg=fg, bg=BG, justify="left", anchor="w", wraplength=wrap,
                      font=("Segoe UI", size, "bold" if bold else "normal"))
        lb.pack(fill="x", padx=10, pady=1)
        return lb

    def show_busy(self, x, y):
        w = self._new(x, y)
        self._label(w, "Checking price...", fg=DIM)
        self._place()

    def show_error(self, x, y, msg, item=None):
        w = self._new(x, y)
        if item is not None and item.name:
            self._label(w, item.headline(), fg=COLORS.get(item.category, FG), size=11, bold=True)
        self._label(w, msg, fg="#e05050")
        if item is not None and item.raw:
            self._label(w, "Read from screen: " + " | ".join(t for t, _ in item.raw[:6]), fg=DIM, size=8)
        self._buttons(w, item, None)
        self._place()

    def _buttons(self, w, item, est):
        bar = tk.Frame(w, bg=BG)
        bar.pack(fill="x", padx=8, pady=(6, 8))
        name = item.market_name if item is not None else ""

        def btn(text, cmd):
            tk.Button(bar, text=text, command=cmd, bg="#25252a", fg=FG, activebackground="#3a3a42",
                      relief="flat", font=("Segoe UI", 9), padx=8).pack(side="left", padx=2)

        def copy_open(url):
            self.root.clipboard_clear()
            self.root.clipboard_append(name)
            webbrowser.open(url)

        if est is not None and est.product_url:
            btn("Traderie", lambda: webbrowser.open(est.product_url))
        if name:
            btn("diablo2.io", lambda: copy_open(D2IO_URL))
            btn("d2jsp", lambda: copy_open(D2JSP_URL))
        btn("Close", self.close)

    def mouse_far_away(self, mx, my, limit):
        """True when the cursor has moved well away from both the item and the result window."""
        if self.win is None:
            return False
        try:
            x0, y0 = self.win.winfo_rootx(), self.win.winfo_rooty()
            x1, y1 = x0 + self.win.winfo_width(), y0 + self.win.winfo_height()
        except Exception:
            return False
        dx = max(x0 - mx, 0, mx - x1)
        dy = max(y0 - my, 0, my - y1)
        ax, ay = self._anchor
        d_anchor = ((mx - ax) ** 2 + (my - ay) ** 2) ** 0.5
        return (dx * dx + dy * dy) ** 0.5 > limit and d_anchor > limit

    @property
    def is_open(self):
        return self.win is not None

    def show_result(self, x, y, item, est):
        w = self._new(x, y)
        runes = est.runes
        self._label(w, item.headline(), fg=COLORS.get(item.category, FG), size=12, bold=True)
        flags = []
        if item.ethereal: flags.append("Ethereal")
        if item.sockets: flags.append(f"{item.sockets} sockets")
        if item.defense: flags.append(f"Def {item.defense}")
        if item.unidentified: flags.append("Unidentified")
        sub = item.category.capitalize() + ("  •  " + ", ".join(flags) if flags else "")
        self._label(w, sub, fg=DIM, size=9)

        if est.median is not None:
            self._label(w, "Estimated value:  " + describe_value(est.median, runes), size=13, bold=True)
            if est.low is not None and est.high is not None and est.high > est.low:
                self._label(w, f"Typical range:  {describe_value(est.low, runes)}  to  {describe_value(est.high, runes)}", size=9)
            fg = self.cfg.get("fg_per_ist")
            ist = runes.get("Ist Rune")
            if fg and ist:
                self._label(w, f"≈ {est.median / ist * float(fg):.0f} FG  (at {fg} FG per Ist, your setting)", fg=DIM, size=9)
        else:
            self._label(w, "No priced trades found for this item.", fg="#e0b030", size=11, bold=True)
        if est.message:
            self._label(w, est.message, fg="#e0b030", size=9)

        conf = est.confidence
        self._label(w, f"Confidence: {conf.upper()}   •   {est.n_sold} recent sales, {est.n_active} active listings"
                    + (f"   •   cheapest similar ask: {describe_value(est.ask_low, runes)}" if est.ask_low else ""),
                    fg=CONF_COLORS[conf], size=9)

        if est.features:
            shown = ", ".join(stat_text(k, v) for k, v in list(est.features.items())[:8])
            self._label(w, "Matched on: " + shown, fg=DIM, size=8)

        if est.comparables:
            pname = est.product.get("name", "") if est.product else ""
            self._label(w, f"Most similar trades of {pname} ({self.cfg['platform']} {self.cfg['mode']} {'Ladder' if self.cfg['ladder'] else 'Non-Ladder'}):" if pname else "Most similar trades:",
                        fg=FG, size=9, bold=True)
            for c in est.comparables:
                rolls = ", ".join(
                    stat_text(k, v) for k, v in c.props.items() if v not in (None, False, "") and k != "Rarity")[:110]
                tag = "SOLD" if c.sold else "ask "
                age = f"{c.age_days:.0f}d" if c.age_days >= 1 else "today"
                self._label(w, f"{tag} {age:>5}  {c.price_text}" + (f"   [{rolls}]" if rolls else ""),
                            fg=FG if c.sold else DIM, size=8, wrap=520)
        self._buttons(w, item, est)
        self._place()
