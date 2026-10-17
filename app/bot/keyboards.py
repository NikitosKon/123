"""Inline-клавиатуры бота."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.formatters import telegram_gift_url
from app.domain.models import DealAnalysis, NormalizedListing


def deal_keyboard(deal: DealAnalysis) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    l = deal.listing
    gift_url = telegram_gift_url(l)
    if gift_url:
        b.row(InlineKeyboardButton(text="🎁 Подарок в Telegram", url=gift_url))
    if l.url:
        b.row(InlineKeyboardButton(text=f"Купить на {l.marketplace.value}", url=l.url))
    b.row(
        InlineKeyboardButton(text="История цен", callback_data=f"hist:{l.marketplace.value}:{l.listing_id}"),
        InlineKeyboardButton(text="Добавить в избранное", callback_data=f"fav:{l.marketplace.value}:{l.listing_id}"),
    )
    b.row(InlineKeyboardButton(text="Скрыть похожие", callback_data=f"mute:{l.variant_fingerprint[:40]}"))
    return b.as_markup()


def listing_keyboard(l: NormalizedListing) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    gift_url = telegram_gift_url(l)
    if gift_url:
        b.row(InlineKeyboardButton(text="🎁 Подарок в Telegram", url=gift_url))
    if l.url:
        b.row(InlineKeyboardButton(text=f"Купить на {l.marketplace.value}", url=l.url))
    b.row(
        InlineKeyboardButton(text="История цен", callback_data=f"hist:{l.marketplace.value}:{l.listing_id}"),
        InlineKeyboardButton(text="В watchlist", callback_data=f"watch:{l.marketplace.value}:{l.listing_id}"),
    )
    b.row(InlineKeyboardButton(text="Мьют", callback_data=f"mute:{l.variant_fingerprint[:40]}"))
    return b.as_markup()


def settings_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="💰 Мин. прибыль", callback_data="set:min_profit"))
    b.row(InlineKeyboardButton(text="📊 Мин. ROI", callback_data="set:min_roi"))
    b.row(InlineKeyboardButton(text="💵 Макс. цена", callback_data="set:max_price"))
    b.row(InlineKeyboardButton(text="🏪 Маркетплейсы", callback_data="set:markets"))
    b.row(InlineKeyboardButton(text="🎁 Коллекции", callback_data="set:collections"))
    b.row(InlineKeyboardButton(text="⏱ Cooldown", callback_data="set:cooldown"))
    return b.as_markup()
