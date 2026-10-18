"""Форматирование текстовых уведомлений бота."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal
from html import escape
from urllib.parse import quote

from app.domain.models import DealAnalysis, FloorQuote, NormalizedListing


def human_age(dt: datetime) -> str:
    sec = max(0, int((datetime.now(timezone.utc) - dt).total_seconds()))
    if sec < 60:
        return f"{sec} секунд назад"
    if sec < 3600:
        return f"{sec // 60} минут назад"
    if sec < 86400:
        return f"{sec // 3600} часов назад"
    return f"{sec // 86400} дней назад"


def fmt_floor(f: FloorQuote | None, label: str, emoji: str) -> str:
    if f is None or f.value is None:
        return f"{emoji} {label}: —"
    conf = " ⚠️ мало данных" if f.listings_count == 1 else ""
    mp = f" ({f.marketplace.value})" if f.marketplace else ""
    return f"{emoji} {label}: {fmt_amount(f.value)} {f.currency.value}{mp}{conf}"


def fmt_amount(value: Decimal) -> str:
    """Format Decimal without redundant trailing zeroes."""
    return format(value.normalize(), "f")


def telegram_gift_url(listing: NormalizedListing) -> str:
    """Вернуть deep link на коллекционный подарок Telegram, если известен номер."""
    raw = listing.raw if isinstance(listing.raw, dict) else {}
    slug = next(
        (raw.get(key) for key in ("telegram_slug", "gift_slug", "slug") if raw.get(key)),
        None,
    )
    if slug:
        slug = str(slug).strip().rstrip("/").split("/")[-1]
    elif listing.gift_num is not None:
        # Telegram collectible links conventionally use CamelCaseGiftName-number.
        words = re.findall(r"[A-Za-z0-9]+", listing.gift_name)
        if not words:
            return ""
        slug = "".join(word[:1].upper() + word[1:] for word in words)
        slug = f"{slug}-{listing.gift_num}"
    else:
        return ""

    if not re.fullmatch(r"[A-Za-z0-9_-]+", slug):
        return ""
    return f"https://t.me/nft/{quote(slug, safe='-_')}"


def format_deal(deal: DealAnalysis) -> str:
    l: NormalizedListing = deal.listing
    transfer = (
        "✅ доступна" if l.transferable is True
        else "⛔ заблокирована" if l.transferable is False
        else "❔ неизвестно"
    )
    name = escape(l.gift_name)
    lines = [
        f"🎁 <b>{name}{f' #{l.gift_num}' if l.gift_num is not None else ''}</b>",
        "",
        f"🛹 Model: {escape(l.model)}" + (f" ({l.model_rarity_pct}%)" if l.model_rarity_pct is not None else ""),
        f"🔵 Backdrop: {escape(l.backdrop)}" + (f" ({l.backdrop_rarity_pct}%)" if l.backdrop_rarity_pct is not None else ""),
        f"🦁 Symbol: {escape(l.symbol)}" + (f" ({l.symbol_rarity_pct}%)" if l.symbol_rarity_pct is not None else ""),
        "",
        f"💎 Цена: {fmt_amount(deal.buy_price)} {l.currency.value} ({l.marketplace.value})",
        f"🔒 Передача: {transfer}",
    ]

    if deal.sell_price is not None:
        sell_market = f" ({deal.sell_marketplace.value})" if deal.sell_marketplace else ""
        lines += [
            "",
            f"💸 Ориентир перепродажи: {fmt_amount(deal.sell_price)} {l.currency.value}"
            f"{sell_market} (активное объявление)",
        ]

    if deal.net_profit is not None:
        profit = f"+{fmt_amount(deal.net_profit)}" if deal.net_profit >= 0 else fmt_amount(deal.net_profit)
        lines += ["", f"💰 Потенциальный профит по этой оценке: ≈ {profit} {l.currency.value}"]
        lines += ["⚠️ Цена перепродажи взята из активных объявлений; продажа по ней не гарантирована."]
    else:
        lines += ["", "💰 Потенциальный профит: нет сравнимой цены перепродажи"]

    lines += [
        fmt_floor(deal.gift_floor, "Флор подарка", "🎁"),
        fmt_floor(deal.model_floor, "Флор модели", "🛹"),
    ]

    gift_url = telegram_gift_url(l)
    if gift_url:
        lines += ["", f'<a href="{escape(gift_url, quote=True)}">🔗 Открыть подарок в Telegram</a>']
    elif l.url:
        lines += ["", f'<a href="{escape(l.url, quote=True)}">🔗 Открыть листинг на {escape(l.marketplace.value)}</a>']
    return "\n".join(lines)


def format_gift_card_caption(l: NormalizedListing) -> str:
    rarity = lambda v: f" ({v}%)" if v else ""  # noqa: E731
    transfer = (
        "✅ доступна" if l.transferable else ("⛔ заблокирована" if l.transferable is not None else "—")
    )
    lines = [
        f"🎁 {l.gift_name} #{l.gift_num}" if l.gift_num else f"🎁 {l.gift_name}",
        "",
        f"🛹 Model: {l.model}{rarity(l.model_rarity_pct)}",
        f"🔵 Backdrop: {l.backdrop}{rarity(l.backdrop_rarity_pct)}",
        f"🦁 Symbol: {l.symbol}{rarity(l.symbol_rarity_pct)}",
        "",
        f"💎 Цена: {l.price} {l.currency.value} ({l.marketplace.value})",
        f"🔒 Передача: {transfer}",
    ]
    if l.availability_issued and l.availability_total:
        issued = f"{l.availability_issued:,}".replace(",", " ")
        total = f"{l.availability_total:,}".replace(",", " ")
        lines.append(f"📊 Availability: {issued}/{total} issued")
    return "\n".join(lines)
