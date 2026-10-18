"""
assets/make_icon.py
Zeichnet das Programm-Icon MangaLibraryV2.ico. build_exe.py gibt es an
"flet pack --icon" weiter; damit bekommen die exe und das Programmfenster
(der mitgepackte Flet-Client) das Icon.

Motiv: eine Reihe Manga-Bände im Regal, jeder Rücken in einer der
Verlagsfarben (colors.py) und mit Bandnummer, ein Lesezeichen
("Gelesen bis") und eine Manga-Sprechblase mit dem "+1" der Kacheln.

Für die kleinen Größen (16-32 px) wird eine vereinfachte Fassung ohne
Schrift gezeichnet, damit das Icon in Explorer und Taskleiste nicht zu
einem Farbbrei verschwimmt.

Nur nötig, wenn das Icon geändert werden soll (braucht Pillow):
    python assets/make_icon.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ICO_FILE = HERE / "MangaLibraryV2.ico"
PREVIEW_FILE = HERE / "MangaLibraryV2.png"

SIZES = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]
SMALL = 32          # bis einschließlich dieser Größe: vereinfachte Fassung
SUPERSAMPLE = 4     # in mehrfacher Größe zeichnen und glatt herunterrechnen

BG_TOP = (44, 62, 112)
BG_BOTTOM = (22, 30, 58)
SHELF = (226, 178, 112)
SHELF_SHADOW = (150, 104, 56)
OUTLINE = (20, 24, 40)
BOOKMARK = (226, 48, 64)

# (Farbe, Höhe relativ, Neigung) - Farben angelehnt an VERLAG_PALETTE (colors.py)
BOOKS = [
    ((92, 219, 118), 0.86, 0),
    ((237, 210, 100), 0.92, 0),
    ((100, 172, 237), 0.80, 0),
    ((250, 138, 112), 0.74, -14),   # angelehnter letzter Band
]


def _font(px):
    for name in ("arialbd.ttf", "seguisb.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, px)
        except OSError:
            continue
    return None


def _darker(color, f=0.72):
    return tuple(int(c * f) for c in color)


def _background(n):
    """Abgerundetes Quadrat mit senkrechtem Farbverlauf."""
    grad = Image.new("RGBA", (n, n))
    px = grad.load()
    for y in range(n):
        t = y / (n - 1)
        row = (*(int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * t) for i in range(3)), 255)
        for x in range(n):
            px[x, y] = row
    mask = Image.new("L", (n, n), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, n - 1, n - 1), radius=int(n * 0.2), fill=255)
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    img.paste(grad, (0, 0), mask)
    return img


def _book(w, h, color, number, detailed, s):
    """Ein Buchrücken als eigenes Bild (damit er sich neigen lässt)."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    line = max(1, int(s * 0.012))
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=int(w * 0.14), fill=color,
                        outline=OUTLINE, width=line)
    dark = _darker(color)
    band = int(h * 0.07)
    # Zierbänder oben und unten
    d.rectangle((line, int(h * 0.08), w - 1 - line, int(h * 0.08) + band), fill=dark)
    d.rectangle((line, h - int(h * 0.08) - band, w - 1 - line, h - int(h * 0.08)), fill=dark)
    if detailed:
        # Lichtkante links
        d.rectangle((line * 2, int(h * 0.04), line * 2 + int(w * 0.1), h - int(h * 0.04)),
                    fill=tuple(min(255, c + 40) for c in color))
        # weißes Etikett mit Bandnummer
        lw = int(w * 0.66)
        lx = (w - lw) // 2
        ly = int(h * 0.30)
        d.rounded_rectangle((lx, ly, lx + lw, ly + lw), radius=int(lw * 0.2),
                            fill=(255, 255, 255), outline=OUTLINE, width=max(1, line // 2))
        font = _font(int(lw * 0.78))
        if font is not None:
            d.text((lx + lw / 2, ly + lw / 2 + lw * 0.03), str(number), font=font,
                   fill=OUTLINE, anchor="mm")
    return img


def _bubble(img, s):
    """Manga-Sprechblase mit "+1" oben rechts."""
    d = ImageDraw.Draw(img)
    line = max(1, int(s * 0.016))
    box = (int(s * 0.55), int(s * 0.07), int(s * 0.94), int(s * 0.36))
    tail = [(int(s * 0.66), int(s * 0.33)), (int(s * 0.60), int(s * 0.45)), (int(s * 0.76), int(s * 0.34))]
    d.polygon(tail, fill=(255, 255, 255), outline=OUTLINE, width=line)
    d.ellipse(box, fill=(255, 255, 255), outline=OUTLINE, width=line)
    # Naht zwischen Blase und Spitze überdecken
    d.polygon([(tail[0][0] + line, tail[0][1] - line * 2), (tail[1][0] + line * 2, tail[1][1] - line * 3),
               (tail[2][0] - line, tail[2][1] - line * 2)], fill=(255, 255, 255))
    font = _font(int(s * 0.17))
    if font is not None:
        cx = (box[0] + box[2]) / 2
        cy = (box[1] + box[3]) / 2
        d.text((cx, cy), "+1", font=font, fill=BOOKMARK, anchor="mm")


def render(size):
    s = size * SUPERSAMPLE
    detailed = size > SMALL
    img = _background(s)
    d = ImageDraw.Draw(img)

    shelf_y = int(s * 0.80)
    shelf_h = int(s * 0.07)
    books = BOOKS if detailed else BOOKS[:3]
    left = int(s * 0.12)
    gap = int(s * 0.015)
    book_w = int(s * (0.16 if detailed else 0.22))
    max_h = int(s * (0.64 if detailed else 0.62))

    x = left
    for number, (color, rel_h, tilt) in enumerate(books, start=1):
        h = int(max_h * rel_h)
        if number == 2:
            # Lesezeichen ragt oben aus Band 2 heraus ("Gelesen bis"), wird
            # vor dem Band gezeichnet, damit der Rücken es unten verdeckt
            bw = int(s * (0.06 if detailed else 0.08))
            bx = x + book_w - bw - int(book_w * 0.12)
            top = shelf_y - h
            tip = top - int(s * 0.11)
            d.polygon([(bx, tip), (bx + bw // 2, tip + int(s * 0.035)), (bx + bw, tip),
                       (bx + bw, top + int(s * 0.03)), (bx, top + int(s * 0.03))],
                      fill=BOOKMARK, outline=OUTLINE, width=max(1, int(s * 0.012)))
        book = _book(book_w, h, color, number, detailed, s)
        if tilt:
            book = book.rotate(tilt, expand=True, resample=Image.BICUBIC)
            img.alpha_composite(book, (x - int(s * 0.005), shelf_y - book.height + int(s * 0.004)))
        else:
            img.alpha_composite(book, (x, shelf_y - h))
        x += book_w + gap

    # Regalbrett
    d.rounded_rectangle((int(s * 0.07), shelf_y, int(s * 0.93), shelf_y + shelf_h),
                        radius=int(shelf_h * 0.3), fill=SHELF, outline=OUTLINE,
                        width=max(1, int(s * 0.012)))
    d.rectangle((int(s * 0.09), shelf_y + int(shelf_h * 0.62), int(s * 0.91), shelf_y + int(shelf_h * 0.8)),
                fill=SHELF_SHADOW)

    if detailed:
        _bubble(img, s)

    return img.resize((size, size), Image.LANCZOS)


def main():
    images = [render(size) for size in SIZES]
    largest = images[-1]
    largest.save(ICO_FILE, format="ICO", sizes=[(n, n) for n in SIZES],
                 append_images=images[:-1])
    largest.save(PREVIEW_FILE)
    print(f"{ICO_FILE.name}: {', '.join(str(n) for n in SIZES)} px")


if __name__ == "__main__":
    main()
