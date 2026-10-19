"""Форматирование текстовых уведомлений бота."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal
from html import escape
from urllib.parse import quote, urlparse

from app.domain.enums import Marketplace
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


def _gift_number(listing: NormalizedListing) -> int | None:
    if listing.gift_num is not None:
        return listing.gift_num
    raw = listing.raw if isinstance(listing.raw, dict) else {}
    for key in ("gift_num", "num", "number", "gift_number", "giftNumber"):
        value = raw.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
        if isinstance(value, str) and value.strip().isdigit() and int(value) > 0:
            return int(value.strip())
    for key in ("name", "title", "gift_name", "collection"):
        match = re.search(r"#\s*(\d+)\s*$", str(raw.get(key) or ""))
        if match:
            return int(match.group(1))
    return None


def telegram_gift_url(listing: NormalizedListing) -> str:
    """Вернуть deep link на коллекционный подарок Telegram, если известен номер."""
    raw = listing.raw if isinstance(listing.raw, dict) else {}
    slug = next(
        (raw.get(key) for key in ("telegram_slug", "gift_slug", "slug") if raw.get(key)),
        None,
    )
    if slug:
        slug = str(slug).strip().rstrip("/").split("/")[-1]
    number = _gift_number(listing)
    if slug:
        slug = re.sub(r"\s*#\s*\d+$", "", slug)
        if number is not None and not re.search(r"-\d+$", slug):
            slug = f"{slug}-{number}"
    elif number is not None:
        # Telegram collectible links conventionally use CamelCaseGiftName-number.
        words = re.findall(r"[A-Za-z0-9]+", listing.gift_name)
        if not words:
            return ""
        slug = "".join(word[:1].upper() + word[1:] for word in words)
        slug = f"{slug}-{number}"
    else:
        return ""

    if not re.fullmatch(r"[A-Za-z0-9_-]+", slug):
        return ""
    return f"https://t.me/nft/{quote(slug, safe='-_')}"


def purchase_url(listing: NormalizedListing) -> str:
    """Надёжная ссылка покупки: используем ссылку адаптера, затем строим fallback."""
    raw = listing.raw if isinstance(listing.raw, dict) else {}
    candidates = [listing.url]
    for key in ("url", "listing_url", "marketplace_url", "link"):
        candidate = raw.get(key)
        if candidate:
            candidates.append(str(candidate))
    for candidate in candidates:
        if not candidate:
            continue
        value = str(candidate).strip()
        if urlparse(value).scheme in {"http", "https"} and urlparse(value).netloc:
            return value

    if listing.marketplace == Marketplace.PORTALS and listing.listing_id:
        return f"https://t.me/portals/market?startapp=gift_{quote(listing.listing_id, safe='')}"
    if listing.marketplace == Marketplace.GETGEMS and listing.listing_id:
        address = str(raw.get("address") or listing.listing_id)
        collection = str(raw.get("collectionAddress") or listing.ton_contract or "")
        if collection:
            return (
                f"https://getgems.io/collection/{quote(collection, safe='')}/"
                f"{quote(address, safe='')}"
            )
        return f"https://getgems.io/nft/{quote(address, safe='')}"
    return ""


def _floor_value(floor: FloorQuote | None) -> str:
    if floor is None or floor.value is None:
        return "—"
    return f"{fmt_amount(floor.value)} {floor.currency.value}"


def format_deal(deal: DealAnalysis) -> str:
    l: NormalizedListing = deal.listing
    transfer = (
        "✅ доступна" if l.transferable is True
        else "⛔ заблокирована" if l.transferable is False
        else "❔ неизвестно"
    )
    name = escape(l.gift_name)
    number = _gift_number(l)
    model_line = " · ".join(
        [
            f"🛹 {escape(l.model or '—')}",
            f"🔵 {escape(l.backdrop or '—')}",
            f"🦁 {escape(l.symbol or '—')}",
        ]
    )
    lines = [
        f"🎁 <b>{name}{f' #{number}' if number is not None else ''}</b>",
        model_line,
        f"💎 Купить: {fmt_amount(deal.buy_price)} {l.currency.value} ({escape(l.marketplace.value)})",
        f"🔒 Передача: {transfer}",
        f"📊 Флор: подарок {_floor_value(deal.gift_floor)} · модель {_floor_value(deal.model_floor)}",
    ]

    if deal.recent_sales_count and deal.recent_sales_median is not None:
        lines.append(
            f"🧾 Продажи за 30 дней: {deal.recent_sales_count} · медиана "
            f"{fmt_amount(deal.recent_sales_median)} {l.currency.value}"
        )

    if deal.net_profit is not None and deal.sell_price is not None:
        profit = f"+{fmt_amount(deal.net_profit)}" if deal.net_profit >= 0 else fmt_amount(deal.net_profit)
        exit_market = f" ({escape(deal.sell_marketplace.value)})" if deal.sell_marketplace else ""
        lines.append(
            f"💰 Потенциал: ≈ {profit} {l.currency.value} · выход "
            f"≈ {fmt_amount(deal.sell_price)} {l.currency.value}{exit_market}"
        )
    else:
        lines.append("💰 Потенциал: нет надёжной оценки выхода")

    gift_url = telegram_gift_url(l)
    buy_url = purchase_url(l)
    links = []
    if gift_url:
        links.append(f'<a href="{escape(gift_url, quote=True)}">🎁 Telegram</a>')
    if buy_url:
        links.append(f'<a href="{escape(buy_url, quote=True)}">🛒 Купить</a>')
    if links:
        lines.extend(["", " · ".join(links)])
    return "\n".join(lines)


def format_gift_card_caption(l: NormalizedListing) -> str:
    rarity = lambda v: f" ({v}%)" if v else ""  # noqa: E731
    transfer = (
        "✅ доступна" if l.transferable else ("⛔ заблокирована" if l.transferable is not None else "—")
    )
    number = _gift_number(l)
    lines = [
        f"🎁 <b>{escape(l.gift_name)}{f' #{number}' if number is not None else ''}</b>",
        " · ".join(
            [
                f"🛹 {escape(l.model or '—')}{rarity(l.model_rarity_pct)}",
                f"🔵 {escape(l.backdrop or '—')}{rarity(l.backdrop_rarity_pct)}",
                f"🦁 {escape(l.symbol or '—')}{rarity(l.symbol_rarity_pct)}",
            ]
        ),
        f"💎 Цена: {fmt_amount(l.price)} {l.currency.value} ({escape(l.marketplace.value)})",
        f"🔒 Передача: {transfer}",
    ]
    if l.availability_issued and l.availability_total:
        issued = f"{l.availability_issued:,}".replace(",", " ")
        total = f"{l.availability_total:,}".replace(",", " ")
        lines.append(f"📊 Выпущено: {issued}/{total}")
    links = []
    gift_url = telegram_gift_url(l)
    buy_url = purchase_url(l)
    if gift_url:
        links.append(f'<a href="{escape(gift_url, quote=True)}">🎁 Telegram</a>')
    if buy_url:
        links.append(f'<a href="{escape(buy_url, quote=True)}">🛒 Купить</a>')
    if links:
        lines.extend(["", " · ".join(links)])
    return "\n".join(lines)
