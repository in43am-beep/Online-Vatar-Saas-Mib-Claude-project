"""Generate 3 placeholder presenter PNGs (960x960). Replace with real avatars."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent / "avatars"

PEOPLE = [
    ("maria.png", "MARIA", (122, 74, 52), "Replace with\nMaria's avatar"),
    ("walter.png", "WALTER", (52, 84, 122), "Replace with\nWalter's avatar"),
    ("priya.png", "PRIYA", (74, 122, 84), "Replace with\nPriya's avatar"),
]


def _font(size):
    for name in ("DejaVuSans-Bold.ttf", "DejaVuSans.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:  # noqa: BLE001
            continue
    return ImageFont.load_default()


def make(fname, name, color, note):
    img = Image.new("RGB", (960, 960), (24, 26, 32))
    d = ImageDraw.Draw(img)
    # head-and-shoulders silhouette
    d.ellipse([330, 180, 630, 480], fill=color)          # head
    d.ellipse([300, 520, 660, 980], fill=(color[0] // 2, color[1] // 2, color[2] // 2))  # shoulders
    fnt = _font(64)
    tw = d.textlength(name, font=fnt)
    d.text(((960 - tw) / 2, 700), name, font=fnt, fill=(232, 228, 218))
    fnt2 = _font(30)
    for i, line in enumerate(note.split("\n")):
        tw = d.textlength(line, font=fnt2)
        d.text(((960 - tw) / 2, 800 + i * 44), line, font=fnt2,
               fill=(138, 143, 158))
    # gold frame
    d.rectangle([8, 8, 952, 952], outline=(212, 162, 78), width=6)
    p = OUT / fname
    OUT.mkdir(parents=True, exist_ok=True)
    img.save(p, "PNG")
    print("wrote", p)


if __name__ == "__main__":
    for args in PEOPLE:
        make(*args)
