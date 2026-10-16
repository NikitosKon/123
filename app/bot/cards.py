"""Рендер визуальной карточки уведомления (Pillow), дизайн по референсу:
тёмный Telegram-стиль, размытый декоративный фон, большая карточка,
синие ссылки, оригинальное изображение подарка, блок аналитики, inline-кнопки.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Sequence

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ---- palette (Telegram dark) ---------------------------------------------
BG = (14, 22, 33)            # фон чата
DOODLE = (26, 40, 56)        # декоративные элементы фона
CARD = (31, 44, 60)          # карточка
PANEL = (22, 32, 44)         # панель изображения
BTN = (24, 37, 51)           # inline-кнопки
WHITE = (245, 248, 251)
GRAY = (139, 154, 173)
BLUE = (111, 177, 240)       # названия/ссылки
GREEN = (76, 199, 112)
RED = (235, 99, 99)
MAGENTA = (224, 93, 166)     # "Telegram" в link-preview
DOTS = (35, 51, 68)

EMOJI_FONT_PATHS = [
    "assets/fonts/NotoColorEmoji.ttf",
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
]
EMOJI_SIZE = 109  # NotoColorEmoji рендерится только в 109px


def _is_emoji(ch: str) -> bool:
    cp = ord(ch)
    return (
        0x1F000 <= cp <= 0x1FAFF
        or 0x2600 <= cp <= 0x27BF
        or 0x2B00 <= cp <= 0x2BFF
        or 0x1F1E6 <= cp <= 0x1F1FF
        or cp in (0x2B50, 0x2B55, 0x3030, 0x203C, 0x2049, 0x2122, 0x2139)
    )


def _graphemes(text: str) -> list[str]:
    """Грубая разбивка на графемы: emoji + VS16/ZWJ-последовательности."""
    out: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if _is_emoji(ch):
            g = ch
            i += 1
            while i < len(text) and (
                text[i] in ("️", "\u200d") or _is_emoji(text[i]) and g.endswith("\u200d")
            ):
                if text[i] == "\u200d" and i + 1 < len(text):
                    g += "\u200d" + text[i + 1]
                    i += 2
                else:
                    g += text[i]
                    i += 1
            out.append(g)
        else:
            out.append(ch)
            i += 1
    return out


@lru_cache(maxsize=256)
def _emoji_bitmap(g: str, target_px: int) -> Image.Image | None:
    for path in EMOJI_FONT_PATHS:
        if Path(path).exists():
            try:
                font = ImageFont.truetype(path, EMOJI_SIZE)
                img = Image.new("RGBA", (EMOJI_SIZE + 8, EMOJI_SIZE + 8), (0, 0, 0, 0))
                d = ImageDraw.Draw(img)
                d.text((4, 4), g, font=font, embedded_color=True)
                bbox = img.getbbox()
                if bbox:
                    img = img.crop(bbox)
                ratio = target_px / img.height
                return img.resize(
                    (max(1, int(img.width * ratio)), target_px), Image.LANCZOS
                )
            except Exception:  # noqa: BLE001,S112
                continue
    return None


def draw_text(
    draw: ImageDraw.ImageDraw,
    img: Image.Image,
    xy: tuple[int, int],
    segments: Sequence[tuple[str, tuple, ImageFont.FreeTypeFont]],
    emoji_px: int | None = None,
) -> int:
    """Рисует строку из сегментов (text, color, font), эмодзи — цветными.
    Возвращает конечный x."""
    x, y = xy
    for text, color, font in segments:
        for g in _graphemes(text):
            if _is_emoji(g[0]):
                px = emoji_px or int(font.size * 1.15)
                bmp = _emoji_bitmap(g, px)
                if bmp is not None:
                    img.paste(bmp, (x, y + int((font.size - px) * 0.35)), bmp)
                    x += bmp.width + 2
                    continue
            draw.text((x, y), g, font=font, fill=color)
            x += int(draw.textlength(g, font=font))
    return x


def text_width(draw: ImageDraw.ImageDraw, segments: Sequence[tuple[str, tuple, ImageFont.FreeTypeFont]], emoji_px: int | None = None) -> int:
    w = 0
    for text, _, font in segments:
        for g in _graphemes(text):
            if _is_emoji(g[0]):
                bmp = _emoji_bitmap(g, emoji_px or int(font.size * 1.15))
                w += (bmp.width + 2) if bmp else int(font.size)
            else:
                w += int(draw.textlength(g, font=font))
    return w


def _rounded(draw: ImageDraw.ImageDraw, box, r, fill, outline=None, width=1):
    draw.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


def _doodle_bg(w: int, h: int, seed: int = 42) -> Image.Image:
    """Размытый декоративный фон с элементами Telegram Gifts."""
    img = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(img)
    rnd = random.Random(seed)
    for _ in range(46):
        x, y = rnd.randint(0, w), rnd.randint(0, h)
        s = rnd.randint(18, 46)
        kind = rnd.choice(["circle", "star", "gift", "candy", "ring"])
        if kind == "circle":
            d.ellipse([x, y, x + s, y + s], outline=DOODLE, width=4)
        elif kind == "ring":
            d.ellipse([x, y, x + s, y + s], outline=DOODLE, width=6)
            d.ellipse([x + s * 0.3, y + s * 0.3, x + s * 0.7, y + s * 0.7], outline=DOODLE, width=3)
        elif kind == "star":
            pts = []
            for k in range(10):
                ang = -math.pi / 2 + k * math.pi / 5
                rr = s if k % 2 == 0 else s * 0.45
                pts.append((x + rr * math.cos(ang), y + rr * math.sin(ang)))
            d.polygon(pts, outline=DOODLE)
        elif kind == "gift":
            d.rounded_rectangle([x, y, x + s, y + s], radius=6, outline=DOODLE, width=4)
            d.line([x + s / 2, y, x + s / 2, y + s], fill=DOODLE, width=4)
            d.line([x, y + s * 0.3, x + s, y + s * 0.3], fill=DOODLE, width=4)
        else:
            d.rounded_rectangle([x, y, x + s, y + s * 0.5], radius=8, outline=DOODLE, width=4)
    img = img.filter(ImageFilter.GaussianBlur(3))
    # виньетка, чтобы фон не отвлекал
    overlay = Image.new("L", (w, h), 90)
    img = Image.composite(img, Image.new("RGB", (w, h), (8, 12, 19)), overlay.point(lambda p: p // 2))
    return img


@dataclass
class CardData:
    gift_name: str
    gift_num: int
    emoji: str = "🎁"
    owner_username: str = ""
    owner_id: int | None = None
    model: str = ""
    model_rarity: str = ""
    backdrop: str = ""
    backdrop_rarity: str = ""
    symbol: str = ""
    symbol_rarity: str = ""
    floor_value: str = ""
    floor_currency: str = "TON"
    floor_updated: str = ""
    transferable: bool | None = None
    availability_issued: int | None = None
    availability_total: int | None = None
    buy_price: str = ""
    gift_floor: str = ""
    model_floor: str = ""
    exact_floor: str = ""
    profit: str = ""
    roi: str = ""
    image_path: Path | None = None
    buttons: list[str] = field(default_factory=list)


def render_card(data: CardData, out_path: Path, *, fonts_dir: str = "assets/fonts") -> Path:
    fonts_dir_p = Path(fonts_dir)
    F = lambda name, size: ImageFont.truetype(str(fonts_dir_p / name), size)  # noqa: E731

    f_title = F("Inter-Bold.ttf", 42)
    f_bold = F("Inter-Bold.ttf", 32)
    f_semi = F("Inter-SemiBold.ttf", 32)
    f_reg = F("Inter-Regular.ttf", 32)
    f_small = F("Inter-Regular.ttf", 28)
    f_italic = F("Inter-Regular.ttf", 28)
    f_btn = F("Inter-SemiBold.ttf", 30)
    f_mag = F("Inter-SemiBold.ttf", 26)

    W = 900
    PAD = 30
    cw = W - 48  # ширина карточки

    dummy = Image.new("RGB", (W, 100))
    dd = ImageDraw.Draw(dummy)

    def seg_line(segs):
        return text_width(dd, segs)

    lines_h = 0
    line_gap = 16

    rows: list[tuple[str, list]] = []
    rows.append(("title", [(f"{data.emoji} {data.gift_name} #{data.gift_num}", BLUE, f_title)]))
    owner_segments: list[tuple[str, tuple, ImageFont.FreeTypeFont]] = [("👤 Owner: ", WHITE, f_semi)]
    if data.owner_username:
        owner_segments.append((f"@{data.owner_username}", BLUE, f_semi))
    if data.owner_id:
        owner_segments.append((f" [ID: {data.owner_id}]", GRAY, f_reg))
    rows.append(("row", owner_segments))
    rows.append(("gap", []))
    if data.model:
        rows.append(("row", [("🛹 Model: ", WHITE, f_semi), (f"{data.model} ", WHITE, f_reg), (f"({data.model_rarity})", GRAY, f_reg)]))
    if data.backdrop:
        rows.append(("row", [("🔵 Backdrop: ", WHITE, f_semi), (f"{data.backdrop} ", WHITE, f_reg), (f"({data.backdrop_rarity})", GRAY, f_reg)]))
    if data.symbol:
        rows.append(("row", [("🦁 Symbol: ", WHITE, f_semi), (f"{data.symbol} ", WHITE, f_reg), (f"({data.symbol_rarity})", GRAY, f_reg)]))
    if data.floor_value:
        rows.append(("gap", []))
        rows.append(("row", [("💎 Флор модели ≈ ", WHITE, f_semi), (f"{data.floor_value} {data.floor_currency} ", WHITE, f_semi), (f"(обновлено {data.floor_updated})", GRAY, f_italic)]))
    if data.transferable is not None:
        rows.append(("gap", []))
        if data.transferable:
            rows.append(("row", [("🔒 Передача: ", WHITE, f_semi), ("✅ доступна", GREEN, f_semi)]))
        else:
            rows.append(("row", [("🔒 Передача: ", WHITE, f_semi), ("⛔ заблокирована", RED, f_semi)]))
    if data.availability_issued is not None and data.availability_total:
        rows.append(("gap", []))
        issued = f"{data.availability_issued:,}".replace(",", " ")
        total = f"{data.availability_total:,}".replace(",", " ")
        rows.append(("row", [("📊 Availability: ", WHITE, f_semi), (f"{issued}", WHITE, f_reg), (f"/{total} issued", GRAY, f_reg)]))

    rows.append(("gap", []))

    # ---- высоты ------------------------------------------------------------
    LINE_H = 46
    content_h = 0
    for kind, segs in rows:
        if kind == "gap":
            content_h += line_gap
        elif kind == "title":
            content_h += 58
        else:
            content_h += LINE_H
    img_panel_h = 560
    analytics_h = 0
    analytics_rows: list[list] = []
    if data.buy_price:
        analytics_rows.append([("💰 Цена покупки: ", WHITE, f_small), (data.buy_price, WHITE, f_small)])
    if data.gift_floor:
        analytics_rows.append([("📈 Gift floor: ", WHITE, f_small), (data.gift_floor, WHITE, f_small)])
    if data.model_floor:
        analytics_rows.append([("💎 Model floor: ", WHITE, f_small), (data.model_floor, WHITE, f_small)])
    if data.exact_floor:
        analytics_rows.append([("🧩 Exact variant floor: ", WHITE, f_small), (data.exact_floor, WHITE, f_small)])
    if data.profit:
        analytics_rows.append([("✅ Потенциальная прибыль: ", WHITE, f_small), (data.profit, GREEN, f_small)])
    if data.roi:
        analytics_rows.append([("📊 ROI: ", WHITE, f_small), (data.roi, GREEN, f_small)])
    if analytics_rows:
        analytics_h = 14 + len(analytics_rows) * 42 + 10

    card_h = PAD + content_h + 18 + img_panel_h + analytics_h + PAD

    btns = data.buttons or ["Открыть подарок", "Купить", "История цен", "Добавить в избранное", "Скрыть похожие"]
    btn_rows = [btns[i : i + 2] for i in range(0, len(btns), 2)]
    btn_h = len(btn_rows) * 68 + (len(btn_rows) - 1) * 12

    tabs_h = 70
    H = tabs_h + card_h + 20 + btn_h + 26

    # ---- render -------------------------------------------------------------
    img = _doodle_bg(W, H)
    d = ImageDraw.Draw(img, "RGBA")

    # верхние pill-табы (стиль быстрых кнопок бота)
    for i, (label, suffix) in enumerate([("Коллекция", ""), ("Модель", "")]):
        tw = int(dd.textlength(label, font=f_semi))
        pw = tw + 96
        px = 14 + i * (pw + 14)
        _rounded(d, [px, 10, px + pw, 62], 26, (24, 37, 51, 235))
        d.ellipse([px + 18, 26, px + 38, 46], fill=(200, 90, 90))
        d.line([px + 24, 36, px + 32, 36], fill=WHITE, width=3)
        d.text((px + 52, 22), label, font=f_semi, fill=WHITE)

    # карточка
    cx0, cy0, cx1 = 24, tabs_h, 24 + cw
    _rounded(d, [cx0, cy0, cx1, cy0 + card_h], 30, CARD)
    # лёгкий верхний блик
    d.rounded_rectangle([cx0, cy0, cx1, cy0 + card_h], radius=30, outline=(255, 255, 255, 14), width=2)

    y = cy0 + PAD
    x_text = cx0 + PAD
    for kind, segs in rows:
        if kind == "gap":
            y += line_gap
            continue
        if kind == "title":
            draw_text(d, img, (x_text, y), segs, emoji_px=44)
            y += 58
        else:
            draw_text(d, img, (x_text, y), segs, emoji_px=34)
            y += LINE_H
    y += 18

    # панель изображения (link-preview стиль)
    px0, px1 = cx0 + 14, cx1 - 14
    pw, ph = px1 - px0, img_panel_h
    _rounded(d, [px0, y, px1, y + ph], 22, PANEL)
    # декоративные точки (как у фона подарка)
    rnd = random.Random(data.gift_num)
    for _ in range(14):
        dx = rnd.randint(px0 + 10, px1 - 30)
        dy = rnd.randint(y + 10, y + ph - 30)
        rr = rnd.randint(6, 14)
        d.ellipse([dx, dy, dx + rr, dy + rr], fill=DOTS)

    if data.image_path and Path(data.image_path).exists():
        try:
            gift = Image.open(data.image_path).convert("RGBA")
            # cover: заполняем всю панель с центрированием и скруглением
            ratio = max(pw / gift.width, ph / gift.height)
            gw, gh = int(gift.width * ratio), int(gift.height * ratio)
            gift = gift.resize((gw, gh), Image.LANCZOS)
            crop = gift.crop(((gw - pw) // 2, (gh - ph) // 2, (gw + pw) // 2, (gh + ph) // 2))
            mask = Image.new("L", (pw, ph), 0)
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, pw, ph], radius=22, fill=255)
            img.paste(crop, (px0, y), mask)
            # затемнение сверху под подписи
            strip = Image.new("RGBA", (pw, 96), (0, 0, 0, 0))
            sd = ImageDraw.Draw(strip)
            for i in range(96):
                sd.line([(0, i), (pw, i)], fill=(10, 16, 24, int(150 * (1 - i / 96))))
            img.paste(strip, (px0, y), strip)
        except Exception:  # noqa: BLE001
            pass
    d.text((px0 + 22, y + 16), "Telegram", font=f_mag, fill=MAGENTA)
    d.text((px0 + 22, y + 50), f"{data.gift_name} #{data.gift_num}", font=f_semi, fill=WHITE)
    y += ph

    # аналитика
    if analytics_rows:
        y += 14
        for segs in analytics_rows:
            draw_text(d, img, (x_text, y), segs, emoji_px=30)
            y += 42

    # кнопки
    by = cy0 + card_h + 20
    bw_gap = 12
    for row in btn_rows:
        n = len(row)
        bw = (cw - (n - 1) * bw_gap) // n
        bx = 24
        for label in row:
            _rounded(d, [bx, by, bx + bw, by + 68], 20, BTN)
            tw = dd.textlength(label, font=f_btn)
            d.text((bx + (bw - tw) / 2, by + 18), label, font=f_btn, fill=BLUE)
            bx += bw + bw_gap
        by += 68 + 12

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG")
    return out_path
