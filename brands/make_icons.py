"""Render the brand PNGs for the Home Assistant brands repository.

Same design language as the other vlios.cz integrations -- a red wordmark with
vlios.cz beneath -- but the shutter slats are replaced by the quantities this
station actually measures: wind speed, temperature, humidity, pressure, gusts
and wind direction.

Run from the repository root::

    python brands/make_icons.py
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

RED = (226, 0, 26, 255)
GREY = (154, 154, 154, 255)
FONT_BOLD = r"C:\Windows\Fonts\ariblk.ttf"

OUT = Path(__file__).parent
# Draw large, then downscale, so the edges come out smooth.
SCALE = 4


def _font(size: int) -> ImageFont.FreeTypeFont:
    """The bold face at a given pixel size."""
    return ImageFont.truetype(FONT_BOLD, int(size * SCALE))


def _fit_font(draw, text, target_w, spacing, start=200):
    """Largest size at which the text still fits the width it is given.

    GIOM is a character wider than the three-letter marks on the sibling
    integrations, so the size is measured rather than hard-coded.
    """
    size = start
    while size > 20:
        font = _font(size)
        widths = [draw.textlength(ch, font=font) for ch in text]
        if sum(widths) + spacing * SCALE * (len(text) - 1) <= target_w * SCALE:
            return font
        size -= 2
    return _font(20)


def _text(draw, xy, text, font, fill, spacing=0) -> None:
    """Draw centred text with optional letter spacing."""
    cx, cy = xy[0] * SCALE, xy[1] * SCALE
    widths = [draw.textlength(ch, font=font) for ch in text]
    total = sum(widths) + spacing * SCALE * (len(text) - 1)
    x = cx - total / 2
    ascent, descent = font.getmetrics()
    y = cy - (ascent + descent) / 2
    for ch, w in zip(text, widths):
        draw.text((x, y), ch, font=font, fill=fill)
        x += w + spacing * SCALE


# --------------------------------------------------------------------------
# Sensor glyphs
#
# Each is drawn inside a box of half-size `r`. The per-glyph multipliers in
# LAYOUT even out the optical weight -- an outlined dial reads lighter than a
# solid droplet at the same nominal size.
# --------------------------------------------------------------------------


def _anemometer(draw, cx, cy, r, fill, rot=-90) -> None:
    """Wind speed."""
    hub, arm_w, arm, cup = r * 0.24, max(2, int(r * 0.15)), r * 0.62, r * 0.36
    for i in range(3):
        a = math.radians(rot + i * 120)
        ex, ey = cx + arm * math.cos(a), cy + arm * math.sin(a)
        draw.line([cx, cy, ex, ey], fill=fill, width=arm_w)
        draw.pieslice(
            [ex - cup, ey - cup, ex + cup, ey + cup],
            start=math.degrees(a) + 90,
            end=math.degrees(a) + 270,
            fill=fill,
        )
    draw.ellipse([cx - hub, cy - hub, cx + hub, cy + hub], fill=fill)


def _thermometer(draw, cx, cy, r, fill) -> None:
    """Temperature."""
    stem_w, bulb_r = r * 0.21, r * 0.40
    bulb_y = cy + r * 0.52
    draw.rounded_rectangle(
        [cx - stem_w, cy - r * 0.90, cx + stem_w, bulb_y], radius=stem_w, fill=fill
    )
    draw.ellipse(
        [cx - bulb_r, bulb_y - bulb_r, cx + bulb_r, bulb_y + bulb_r], fill=fill
    )
    for i, ty in enumerate((-0.55, -0.25, 0.05)):
        length = r * (0.40 if i % 2 == 0 else 0.26)
        draw.line(
            [cx + stem_w + r * 0.16, cy + r * ty,
             cx + stem_w + r * 0.16 + length, cy + r * ty],
            fill=fill,
            width=max(2, int(r * 0.11)),
        )


def _droplet(draw, cx, cy, r, fill) -> None:
    """Humidity."""
    ball_r = r * 0.55
    ball_y = cy + r * 0.30
    draw.polygon(
        [
            (cx, cy - r * 0.92),
            (cx - ball_r * 0.86, ball_y + ball_r * 0.16),
            (cx + ball_r * 0.86, ball_y + ball_r * 0.16),
        ],
        fill=fill,
    )
    draw.ellipse(
        [cx - ball_r, ball_y - ball_r, cx + ball_r, ball_y + ball_r], fill=fill
    )


def _barometer(draw, cx, cy, r, fill) -> None:
    """Pressure."""
    ring_r = r * 0.82
    draw.ellipse(
        [cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r],
        outline=fill,
        width=max(2, int(r * 0.20)),
    )
    a = math.radians(-52)
    draw.line(
        [cx, cy, cx + ring_r * 0.62 * math.cos(a), cy + ring_r * 0.62 * math.sin(a)],
        fill=fill,
        width=max(2, int(r * 0.17)),
    )
    hub = r * 0.15
    draw.ellipse([cx - hub, cy - hub, cx + hub, cy + hub], fill=fill)


def _windlines(draw, cx, cy, r, fill) -> None:
    """Gusts."""
    thick = r * 0.22
    for dy, half in ((-0.48, 0.78), (0.02, 0.95), (0.52, 0.60)):
        y = cy + r * dy
        draw.rounded_rectangle(
            [cx - r * half, y - thick / 2, cx + r * half, y + thick / 2],
            radius=thick / 2,
            fill=fill,
        )


def _compass(draw, cx, cy, r, fill, rot=-38) -> None:
    """Wind direction."""
    pts = [(0, -0.95), (-0.60, 0.78), (0, 0.30), (0.60, 0.78)]
    a = math.radians(rot)
    ca, sa = math.cos(a), math.sin(a)
    draw.polygon(
        [(cx + (px * ca - py * sa) * r, cy + (px * sa + py * ca) * r) for px, py in pts],
        fill=fill,
    )


# glyph, optical-weight multiplier
LAYOUT = (
    (_anemometer, 1.10),
    (_thermometer, 0.98),
    (_droplet, 0.94),
    (_barometer, 1.04),
    (_windlines, 1.00),
    (_compass, 1.12),
)


def _sensor_rows(draw, xs, ys, r) -> None:
    """Lay the six glyphs across two rows, in place of the slats."""
    for row, y in enumerate(ys):
        for col, x in enumerate(xs):
            glyph, weight = LAYOUT[row * len(xs) + col]
            glyph(draw, x * SCALE, y * SCALE, r * weight * SCALE, GREY)


def _trim_square(img: Image.Image, margin: float) -> Image.Image:
    """Crop to the drawn content and centre it on a square canvas."""
    bbox = img.getbbox()
    if bbox is None:
        return img
    content = img.crop(bbox)
    side = round(max(content.size) / (1 - 2 * margin))
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(content, ((side - content.width) // 2, (side - content.height) // 2))
    return canvas


def render_icon() -> Image.Image:
    """The square icon: sensors, GIOM, vlios.cz, trimmed to fill the square."""
    size = 512
    img = Image.new("RGBA", (size * SCALE, size * SCALE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    _sensor_rows(draw, (152, 256, 360), (148, 368), 48)
    _text(draw, (256, 256), "GIOM", _fit_font(draw, "GIOM", 330, 6), RED, spacing=6)
    _text(draw, (256, 456), "vlios.cz", _font(50), RED, spacing=4)

    return _trim_square(img, margin=0.06)


def render_logo() -> Image.Image:
    """The wide logo, for the config dialog."""
    w, h = 720, 400
    img = Image.new("RGBA", (w * SCALE, h * SCALE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    _sensor_rows(draw, (232, 360, 488), (78, 300), 44)
    _text(draw, (360, 192), "GIOM", _fit_font(draw, "GIOM", 400, 8), RED, spacing=8)
    _text(draw, (360, 372), "vlios.cz", _font(56), RED, spacing=5)

    return img.resize((w, h), Image.LANCZOS)


def _save(image: Image.Image, name: str, big: int) -> None:
    """Write name.png at `big` and name@2x.png at twice that."""
    ratio = image.width / image.height
    for suffix, target in (("", big), ("@2x", big * 2)):
        out = image.resize((round(target * ratio), target), Image.LANCZOS)
        out.save(OUT / f"{name}{suffix}.png")
        print(f"  {name}{suffix}.png {out.size}")


def main() -> None:
    """Render every brand file."""
    print("Rendering brand assets:")
    _save(render_icon(), "icon", 256)
    _save(render_logo(), "logo", 256)


if __name__ == "__main__":
    main()
