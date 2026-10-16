"""Форматирование текстовых уведомлений бота."""
from __future__ import annotations

from datetime import datetime, timezone

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
    conf = " ⚠️ low confidence" if f.listings_count == 1 else ""
    mp = f" ({f.marketplace.value})" if f.marketplace else ""
    return f"{emoji} {label}: {f.value} {f.currency.value}{mp}{conf}"


def format_deal(deal: DealAnalysis) -> str:
    l: NormalizedListing = deal.listing
    lines = [
        "🟢 <b>NEW DEAL</b>",
        "",
        f"🎁 Gift: {l.gift_name}" + (f" #{l.gift_num}" if l.gift_num else ""),
        f"🧩 Model: {l.model}" + (f" ({l.model_rarity_pct}%)" if l.model_rarity_pct else ""),
        f"🎨 Backdrop: {l.backdrop}" + (f" ({l.backdrop_rarity_pct}%)" if l.backdrop_rarity_pct else ""),
        f"🔹 Symbol: {l.symbol}" + (f" ({l.symbol_rarity_pct}%)" if l.symbol_rarity_pct else ""),
    ]
    if l.gift_num:
        lines.append(f"🔢 Number: #{l.gift_num}")
    lines += [
        "",
        f"💰 Купить:\n{deal.buy_price} {l.currency.value} на {deal.buy_marketplace.value}",
    ]
    if deal.sell_price is not None:
        mp = deal.sell_marketplace.value if deal.sell_marketplace else "—"
        lines.append(f"\n📈 Продать:\n{deal.sell_price} {l.currency.value} на {mp}")
    lines.append("")
    lines.append(fmt_floor(deal.gift_floor, "Gift floor", "💎"))
    lines.append(fmt_floor(deal.model_floor, "Model floor", "🧩"))
    lines.append(fmt_floor(deal.exact_variant_floor, "Exact variant floor", "🎨"))
    lines.append("")
    lines.append(f"💸 Все расходы: {deal.total_costs} {l.currency.value}")
    if deal.net_profit is not None:
        sign = "+" if deal.net_profit >= 0 else ""
        lines.append(f"✅ Net profit: {sign}{deal.net_profit} {l.currency.value} ({deal.status})")
    if deal.roi_percent is not None:
        sign = "+" if deal.roi_percent >= 0 else ""
        lines.append(f"📊 ROI: {sign}{deal.roi_percent}%")
    lines += [
        "",
        f"🟡 Confidence: {deal.confidence.value}",
        f"🕒 Обновлено: {human_age(deal.updated_at)}",
    ]
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
