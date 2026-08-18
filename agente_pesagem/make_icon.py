"""Gera sao_geraldo.ico a partir do logo da empresa (emblema circular)."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
SRC = REPO / "static" / "img" / "logo.png"
ICO = ROOT / "sao_geraldo.ico"
PNG = ROOT / "sao_geraldo.png"
SIZES = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def _is_colorful(r: int, g: int, b: int, a: int) -> bool:
    if a < 10:
        return False
    mx, mn = max(r, g, b), min(r, g, b)
    return (mx - mn) >= 25 and mx >= 40


def _emblem_crop(im: Image.Image) -> Image.Image:
    """Recorta o emblema circular à esquerda do logo (texto fica de fora)."""
    rgba = im.convert("RGBA")
    w, h = rgba.size
    px = rgba.load()
    # Slogan ocupa a faixa inferior; ignorar para achar o vão emblema/texto.
    y_limit = int(h * 0.72)
    counts = []
    for x in range(w):
        c = 0
        for y in range(y_limit):
            r, g, b, a = px[x, y]
            if _is_colorful(r, g, b, a):
                c += 1
        counts.append(c)

    # O emblema é o primeiro bloco denso; depois vem um vão e o texto.
    start = next((i for i, c in enumerate(counts) if c > 20), 0)
    gap = None
    in_gap = 0
    for x in range(start + 20, min(w, start + h + 40)):
        if counts[x] < 8:
            in_gap += 1
            if in_gap >= 8:
                gap = x - in_gap + 1
                break
        else:
            in_gap = 0
    end = gap if gap else min(w, start + h)

    minx, miny, maxx, maxy = end, y_limit, start, 0
    for y in range(y_limit):
        for x in range(start, end):
            r, g, b, a = px[x, y]
            if _is_colorful(r, g, b, a):
                minx = min(minx, x)
                miny = min(miny, y)
                maxx = max(maxx, x)
                maxy = max(maxy, y)

    pad = 10
    minx = max(0, minx - pad)
    miny = max(0, miny - pad)
    maxx = min(w - 1, maxx + pad)
    maxy = min(h - 1, maxy + pad)
    side = max(maxx - minx + 1, maxy - miny + 1)
    cx = (minx + maxx) // 2
    cy = (miny + maxy) // 2
    left = max(0, cx - side // 2)
    top = max(0, cy - side // 2)
    right = min(w, left + side)
    bottom = min(h, top + side)
    left = max(0, right - side)
    top = max(0, bottom - side)
    crop = rgba.crop((left, top, right, bottom))

    # Fundo branco (o logo original não tem transparência)
    sq = Image.new("RGBA", (side, side), (255, 255, 255, 255))
    sq.paste(crop, (0, 0), crop)
    return sq


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"Logo não encontrado: {SRC}")
    emblem = _emblem_crop(Image.open(SRC))
    emblem.save(PNG, format="PNG")
    # Salvar a partir da imagem cheia. Gravar ICO a partir do 16x16 gerava ~800 bytes
    # e o Windows/Tk caía no ícone padrão (disquete Python).
    emblem.resize((256, 256), Image.Resampling.LANCZOS).save(
        ICO,
        format="ICO",
        sizes=SIZES,
    )
    print(f"ICO: {ICO}")
    print(f"PNG: {PNG}")


if __name__ == "__main__":
    main()
