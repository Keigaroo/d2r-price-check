"""Text recognition with the OCR engine built into Windows 10/11, plus text-colour detection.

D2R tooltips are coloured text on a dark box. We feed Windows OCR an enlarged, inverted,
high-contrast copy (dark text on white), and read each line's colour from the original pixels.
"""
import asyncio
import colorsys
from dataclasses import dataclass, field

from PIL import Image, ImageOps


@dataclass
class Line:
    text: str
    x: float
    y: float
    w: float
    h: float
    color: str = "unknown"
    rgb: tuple = (0, 0, 0)
    words: list = field(default_factory=list)

    @property
    def cx(self):
        return self.x + self.w / 2

    @property
    def bottom(self):
        return self.y + self.h


def _prepare(img: Image.Image, scale: float) -> Image.Image:
    # Brightest channel makes blue/green/gold text equally bright.
    r, g, b = img.split()
    from PIL import ImageChops
    gray = ImageChops.lighter(ImageChops.lighter(r, g), b)
    gray = ImageOps.autocontrast(gray, cutoff=1)
    gray = ImageOps.invert(gray)
    if scale != 1:
        gray = gray.resize((int(gray.width * scale), int(gray.height * scale)), Image.LANCZOS)
    return gray.convert("RGBA")


def _run_windows_ocr(img_rgba: Image.Image):
    from winrt.windows.globalization import Language
    from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.storage.streams import DataWriter

    lang = Language("en-US")
    if not OcrEngine.is_language_supported(lang):
        raise RuntimeError(
            "Windows English OCR is not installed. Run this in an Administrator PowerShell:\n"
            'Add-WindowsCapability -Online -Name "Language.OCR~~~en-US~0.0.1.0"')
    writer = DataWriter()
    writer.write_bytes(img_rgba.tobytes())
    sb = SoftwareBitmap.create_copy_from_buffer(
        writer.detach_buffer(), BitmapPixelFormat.RGBA8, img_rgba.width, img_rgba.height)
    engine = OcrEngine.try_create_from_language(lang)

    async def go():
        return await engine.recognize_async(sb)
    return asyncio.run(go())


def max_dimension():
    try:
        from winrt.windows.media.ocr import OcrEngine
        return int(OcrEngine.max_image_dimension)
    except Exception:
        return 10000


def classify_color(rgb):
    """Map an average text colour to a D2R item-quality colour name."""
    r, g, b = [c / 255 for c in rgb]
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    hue = h * 360
    if v < 0.25:
        return "unknown"
    if s < 0.18:
        return "white" if v > 0.62 else "gray"
    if hue < 15 or hue >= 340:
        return "red"
    if hue < 50 and s > 0.8:
        return "orange"      # crafted items, runes (fully saturated)
    # Unique gold sits at ~45 deg, rare yellow at ~60 deg. Judge by hue only: brightness varies
    # (a tooltip that is still fading in can be half as bright).
    if hue < 52:
        return "gold"        # unique / runeword names (muted tan)
    if hue < 75:
        return "yellow"
    if hue < 170:
        return "green"       # set items
    if hue < 270:
        return "blue"        # magic items, stat text
    return "unknown"


def _line_rgb(img: Image.Image, x, y, w, h):
    box = (max(0, int(x)), max(0, int(y)), min(img.width, int(x + w)), min(img.height, int(y + h)))
    if box[2] <= box[0] or box[3] <= box[1]:
        return (0, 0, 0)
    crop = img.crop(box)
    px = list(crop.getdata())
    # Text pixels are the brightest ones; take the brightest 15%.
    px.sort(key=lambda p: max(p), reverse=True)
    top = px[: max(1, len(px) * 15 // 100)]
    n = len(top)
    return tuple(sum(p[i] for p in top) // n for i in range(3))


def read_lines(img: Image.Image, screen_height: int):
    """OCR an RGB screenshot. Returns a list of Line objects in the screenshot's coordinates."""
    # Aim for ~28-34 px tall text for the OCR engine. D2R text is ~1.9% of screen height.
    scale = max(1.0, min(3.0, 32 / max(1.0, screen_height * 0.019)))
    limit = max_dimension()
    scale = min(scale, limit / max(img.width, img.height))
    prepared = _prepare(img, scale)
    result = _run_windows_ocr(prepared)
    lines = []
    for ln in result.lines:
        words = []
        for w in ln.words:
            br = w.bounding_rect
            words.append((w.text, br.x / scale, br.y / scale, br.width / scale, br.height / scale))
        if not words:
            continue
        x0 = min(w[1] for w in words)
        y0 = min(w[2] for w in words)
        x1 = max(w[1] + w[3] for w in words)
        y1 = max(w[2] + w[4] for w in words)
        rgb = _line_rgb(img, x0, y0, x1 - x0, y1 - y0)
        lines.append(Line(ln.text, x0, y0, x1 - x0, y1 - y0, classify_color(rgb), rgb, words))
    return lines


def _span(blk):
    return min(l.x for l in blk), max(l.x + l.w for l in blk)


def _same_column(ln, blk, med_h):
    """Does this line belong to the same centred text column as the block?

    Tooltip lines are centred, but OCR sometimes drops a word ('+1 to Mana' -> 'to Mana'),
    which shifts a line's centre. So accept either a close centre, or a line that lies
    mostly inside the block's horizontal span (or the block inside the line)."""
    bx0, bx1 = _span(blk)
    centre = (bx0 + bx1) / 2
    if abs(ln.cx - centre) <= max(14, 1.6 * med_h, 0.15 * max(ln.w, bx1 - bx0)):
        return True
    overlap = min(ln.x + ln.w, bx1) - max(ln.x, bx0)
    return overlap >= 0.7 * min(ln.w, bx1 - bx0)


def tooltip_candidates(lines, cursor_x, cursor_y):
    """Group OCR lines into centred text blocks; return them nearest-to-cursor first."""
    if not lines:
        return []
    lines = sorted(lines, key=lambda l: l.y)
    med_h = sorted(l.h for l in lines)[len(lines) // 2]
    # Ignore specks (window buttons like 'o' / 'x', single stray characters).
    lines = [l for l in lines if len(l.text.replace(" ", "")) >= 2 and l.h >= 0.6 * med_h]
    blocks = []
    for ln in lines:
        for blk in blocks:
            gap = ln.y - blk[-1].bottom
            if -0.5 * med_h <= gap <= 2.2 * med_h and _same_column(ln, blk, med_h):
                blk.append(ln)
                break
        else:
            blocks.append([ln])

    # Second pass: glue together blocks stacked directly on top of each other in the same column
    # (a tooltip split in two by one badly read line).
    merged = True
    while merged:
        merged = False
        blocks.sort(key=lambda b: b[0].y)
        for i in range(len(blocks) - 1):
            a, b = blocks[i], blocks[i + 1]
            gap = b[0].y - a[-1].bottom
            ax0, ax1 = _span(a)
            bx0, bx1 = _span(b)
            overlap = min(ax1, bx1) - max(ax0, bx0)
            if -0.5 * med_h <= gap <= 2.2 * med_h and overlap >= 0.6 * min(ax1 - ax0, bx1 - bx0) \
                    and abs((ax0 + ax1) / 2 - (bx0 + bx1) / 2) <= 0.2 * max(ax1 - ax0, bx1 - bx0) + med_h:
                blocks[i] = a + b
                del blocks[i + 1]
                merged = True
                break

    def dist(blk):
        x0, x1 = _span(blk)
        y0 = min(l.y for l in blk); y1 = max(l.bottom for l in blk)
        dx = max(x0 - cursor_x, 0, cursor_x - x1)
        dy = max(y0 - cursor_y, 0, cursor_y - y1)
        return (dx * dx + dy * dy) ** 0.5 - 3 * med_h * min(len(blk), 6)

    return sorted(blocks, key=dist)


def pick_tooltip(lines, cursor_x, cursor_y):
    c = tooltip_candidates(lines, cursor_x, cursor_y)
    return c[0] if c else []
