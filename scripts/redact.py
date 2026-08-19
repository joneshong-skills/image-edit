"""Background-sample redaction — de-identify screenshots naturally.

Instead of mosaic/blur (which screams "censored"), this samples the local
background colour, fills over the original text, and writes a fake replacement
in its place — so the result looks like a genuine screenshot of a fake account.
Avatars become flat monogram circles (default-avatar style).

Design split (keeps the pure-pixel / orchestration boundary clean):
  - This module owns the *mechanical* primitives that are fiddly by hand:
    robust background sampling, auto-measuring the real text extent (so fill
    boxes never clip), font fallback, fill+write, monogram avatars, and a
    small fake-identity generator.
  - The *decisions* (which regions, what replacement text) stay with the
    caller — OCR can auto-locate ASCII emails, but region/name choices are a
    judgement call left to the orchestration layer.

CLI (auto path — redacts every email it can OCR):
    python3 redact.py <image> [--out OUT]

Module:
    from redact import RedactCanvas, fake_identities
    c = RedactCanvas("shot.png")
    c.auto_redact_emails()                       # OCR + regex, auto-measured
    c.redact_text((222,1142,645,1192), "小華")    # manual region, auto-measured
    c.monogram_avatar(148, 1193, 54, "華")
    c.save("shot_deid.png")
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# --- Google dark-theme palette (matches most dark-mode app UIs) -------------
PRIMARY_TEXT = (232, 234, 237)  # names, headings
SECONDARY_TEXT = (154, 160, 166)  # emails, captions
WHITE = (255, 255, 255)

# Flat monogram colours, cycled in order (Material-ish, distinct hues).
MONOGRAM_COLORS = [
    (26, 115, 232),
    (217, 48, 37),
    (30, 142, 62),
    (227, 116, 0),
    (147, 52, 230),
    (0, 137, 123),
    (197, 57, 110),
    (24, 128, 156),
]

# Font fallback chains — first existing path wins. CJK is required for names;
# Latin falls back to PIL's bundled DejaVuSans so emails always render.
_CJK_FONTS = [
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
]
_LATIN_FONTS = [
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _resolve(paths: list[str]) -> str | None:
    for p in paths:
        if Path(p).exists():
            return p
    return None


_CJK_PATH = _resolve(_CJK_FONTS)
_LATIN_PATH = _resolve(_LATIN_FONTS)


def font(kind: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """kind: 'cjk' | 'latin'. Falls back to PIL's bundled font if none found."""
    path = _CJK_PATH if kind == "cjk" else (_LATIN_PATH or _CJK_PATH)
    if path is None:
        if kind == "cjk":
            raise RuntimeError("No CJK font found. Install one of: " + ", ".join(_CJK_FONTS))
        return ImageFont.load_default()
    return ImageFont.truetype(path, size)


# --- Fake identity generation ----------------------------------------------
# name -> (monogram char, email local-part). Cycled by fake_identities().
_FAKE_POOL = [
    ("小明", "明", "xiaoming"),
    ("小華", "華", "xiaohua"),
    ("小美", "美", "xiaomei"),
    ("小王", "王", "xiaowang"),
    ("小李", "李", "xiaoli"),
    ("小芳", "芳", "xiaofang"),
    ("小強", "強", "xiaoqiang"),
    ("小婷", "婷", "xiaoting"),
    ("小傑", "傑", "xiaojie"),
    ("小芬", "芬", "xiaofen"),
]


@dataclass
class FakeIdentity:
    name: str
    monogram: str
    email: str
    color: tuple[int, int, int]


def fake_identities(n: int, domain: str = "gmail.com") -> list[FakeIdentity]:
    """Return n distinct fake identities (cycles the pool if n exceeds it)."""
    out = []
    for i in range(n):
        name, mono, local = _FAKE_POOL[i % len(_FAKE_POOL)]
        suffix = "" if i < len(_FAKE_POOL) else str(i // len(_FAKE_POOL) + 1)
        out.append(
            FakeIdentity(
                name=name,
                monogram=mono,
                email=f"{local}{suffix}@{domain}",
                color=MONOGRAM_COLORS[i % len(MONOGRAM_COLORS)],
            )
        )
    return out


_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


class RedactCanvas:
    """A loaded image you redact in place, then save."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.im = Image.open(self.path).convert("RGB")
        self.arr = np.array(self.im)
        self.draw = ImageDraw.Draw(self.im)

    # -- pixel primitives ----------------------------------------------------
    def sample_bg(self, rect) -> tuple[int, int, int]:
        """Median colour of the rect's top+bottom edge strips.

        Works because text is padded away from a box's top/bottom edges, so the
        edge rows are pure background — adapts per-container automatically
        (header sheet vs card vs body all differ).
        """
        x1, y1, x2, y2 = (int(v) for v in rect)
        k = max(2, (y2 - y1) // 12)
        strip = np.vstack([self.arr[y1 : y1 + k, x1:x2], self.arr[y2 - k : y2, x1:x2]]).reshape(
            -1, 3
        )
        m = np.median(strip, axis=0)
        return (int(m[0]), int(m[1]), int(m[2]))

    def measure_bounds(self, rect, bg=None, thresh: int = 45):
        """Detect the real horizontal text span inside rect (x_min, x_max).

        Solves hand-estimated fill boxes that clip glyph tails: scan columns for
        pixels deviating from background by > thresh. Returns None if the band is
        empty (already background).
        """
        x1, y1, x2, y2 = (int(v) for v in rect)
        if bg is None:
            bg = self.sample_bg(rect)
        band = self.arr[y1:y2, x1:x2].astype(int)
        dev = np.abs(band - np.array(bg)).sum(axis=2) > thresh
        cols = np.where(dev.any(axis=0))[0]
        if len(cols) == 0:
            return None
        return (x1 + int(cols.min()), x1 + int(cols.max()))

    # -- composite operations ------------------------------------------------
    def redact_text(
        self, rect, text, *, kind="cjk", size=None, color=PRIMARY_TEXT, align="l", pad=8
    ):
        """Auto-measure the real text extent, fill it, write `text` in place.

        `rect` is a rough bounding box; the actual fill width auto-expands to the
        measured glyph span (+pad) so nothing is left behind. size defaults to
        ~0.62 * box height.
        """
        x1, y1, x2, y2 = (int(v) for v in rect)
        bg = self.sample_bg(rect)
        bounds = self.measure_bounds(rect, bg=bg)
        fx1, fx2 = (min(x1, bounds[0] - pad), max(x2, bounds[1] + pad)) if bounds else (x1, x2)
        fx1 = max(0, fx1)
        fx2 = min(self.im.width, fx2)
        self.draw.rectangle((fx1, y1, fx2, y2), fill=bg)
        if size is None:
            size = int((y2 - y1) * 0.62)
        fnt = font(kind, size)
        my = (y1 + y2) // 2
        if align == "c":
            self.draw.text(((x1 + x2) // 2, my), text, font=fnt, fill=color, anchor="mm")
        else:
            self.draw.text((x1 + 4, my), text, font=fnt, fill=color, anchor="lm")

    def auto_redact_emails(self, replacer=None, *, conf=40):
        """OCR the image, redact every email-shaped token found.

        replacer: callable(index, original_text) -> replacement string.
                  Defaults to xiaoming@ / xiaohua@ ... cycling the fake pool.
        Returns the list of (original, replacement, rect) redacted.
        """
        import pytesseract  # lazy: only needed for the auto path

        data = pytesseract.image_to_data(self.im, output_type=pytesseract.Output.DICT)
        ids = fake_identities(64)
        done = []
        n = 0
        for i in range(len(data["text"])):
            tok = data["text"][i].strip()
            if not tok or data["conf"][i] < conf or not _EMAIL_RE.fullmatch(tok):
                continue
            x, y, w, h = (data["left"][i], data["top"][i], data["width"][i], data["height"][i])
            rect = (x - 4, y - 6, x + w + 4, y + h + 6)
            rep = replacer(n, tok) if replacer else ids[n].email
            self.redact_text(rect, rep, kind="latin", size=int(h * 0.95), color=SECONDARY_TEXT)
            done.append((tok, rep, rect))
            n += 1
        return done

    def monogram_avatar(self, cx, cy, r, char, color=None, *, idx=0):
        """Replace a circular avatar with a flat colour disc + a letter."""
        if color is None:
            color = MONOGRAM_COLORS[idx % len(MONOGRAM_COLORS)]
        self.draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
        self.draw.text((cx, cy), char, font=font("cjk", int(r * 1.25)), fill=WHITE, anchor="mm")

    def save(self, out=None):
        out = Path(out) if out else self.path.with_name(self.path.stem + "_deid.png")
        self.im.save(out)
        return out


def _cli():
    import argparse

    ap = argparse.ArgumentParser(description="Auto-redact emails in a screenshot.")
    ap.add_argument("image")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    c = RedactCanvas(args.image)
    done = c.auto_redact_emails()
    out = c.save(args.out)
    print(f"redacted {len(done)} email(s) -> {out}")
    for orig, rep, _ in done:
        print(f"  {orig}  ->  {rep}")


if __name__ == "__main__":
    _cli()
