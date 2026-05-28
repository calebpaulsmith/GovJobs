"""Generate FedFinder PWA icons (PNG) from the favicon's magnifier glyph.

No SVG rasterizer is available in this environment, so the glyph is redrawn
with Pillow at 4x supersampling and downscaled (LANCZOS) for crisp edges.
Mirrors public_map/static/favicon.svg: dark rounded tile (#0e1726) + an accent
(#7bd0f2) circle-and-stem mark. Re-run to regenerate.

    python scripts/gen_pwa_icons.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "public_map" / "static"
BG = (14, 23, 38, 255)        # #0e1726
ACCENT = (123, 208, 242, 255)  # #7bd0f2
SS = 4  # supersample factor


def _draw(size: int, *, maskable: bool) -> Image.Image:
    s = size * SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Background. Maskable + apple icons need a full-bleed square (the OS masks
    # the shape); the "any" icons get rounded corners to look right unmasked.
    if maskable:
        d.rectangle([0, 0, s - 1, s - 1], fill=BG)
    else:
        d.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.18), fill=BG)

    # Glyph in favicon (32-unit) coordinates, scaled to the canvas.
    u = s / 32.0
    sw = max(2, round(2 * u))
    cx, cy, r = 16 * u, 13 * u, 6 * u
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=ACCENT, width=sw)
    d.line([(16 * u, 19 * u), (16 * u, 27 * u)], fill=ACCENT, width=sw)
    d.line([(11 * u, 27 * u), (21 * u, 27 * u)], fill=ACCENT, width=sw)
    # Round the stroke caps with small filled circles.
    for px, py in [(16 * u, 19 * u), (16 * u, 27 * u), (11 * u, 27 * u), (21 * u, 27 * u)]:
        rr = sw / 2
        d.ellipse([px - rr, py - rr, px + rr, py + rr], fill=ACCENT)

    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    _draw(192, maskable=False).save(OUT / "icon-192.png")
    _draw(512, maskable=False).save(OUT / "icon-512.png")
    _draw(512, maskable=True).save(OUT / "icon-maskable-512.png")
    # apple-touch-icon: 180px, opaque (iOS adds its own rounding).
    _draw(180, maskable=True).convert("RGB").save(OUT / "apple-touch-icon.png")
    print(f"Wrote PWA icons to {OUT}")


if __name__ == "__main__":
    main()
