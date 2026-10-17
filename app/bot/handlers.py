"""Обработчики команд бота (aiogram 3.x)."""
from __future__ import annotations

import logging
from decimal import Decimal

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from app.adapters import build_adapters
from app.bot.cards import CardData, render_card
from app.bot.formatters import format_deal, format_gift_card_caption
from app.bot.keyboards import deal_keyboard, listing_keyboard, settings_keyboard
from app.config import Settings
from app.domain.enums import SourceStatus
from app.services.dedup import DedupStore
from app.services.images import GiftImageService
from app.services.profit import analyze_deal, is_worth_alert

log = logging.getLogger(__name__)
router = Router()

HELP = (
    "🤖 <b>Gift Deals Aggregator</b>\n\n"
    "/latest — последние листинги\n"
    "/deals — выгодные предложения\n"
    "/top — топ по ROI\n"
    "/gift &lt;название&gt; — поиск подарка\n"
    "/watchlist — ваш watchlist\n"
    "/filters — ваши фильтры\n"
    "/markets — статус маркетплейсов\n"
    "/history — история цен\n"
    "/settings — настройки\n"
    "/help — помощь"
)


class BotContext:
    """Общий контекст приложения для хендлеров и воркеров."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.adapters = build_adapters(settings)
        self.images = GiftImageService(
            bot_token=settings.bot_token,
            tonapi_key=settings.tonapi_key,
            cache_dir=settings.image_cache_dir,
        )
        self.dedup = DedupStore()


_ctx: BotContext | None = None


def setup_dispatcher(settings: Settings) -> Dispatcher:
    global _ctx
    _ctx = BotContext(settings)
    dp = Dispatcher()
    dp.include_router(router)
    return dp


def ctx() -> BotContext:
    if _ctx is None:
        raise RuntimeError("Bot context is not initialized; call setup_dispatcher first")
    return _ctx


@router.message(CommandStart())
async def cmd_start(m: Message) -> None:
    await m.answer(
        "👋 Привет! Я слежу за маркетплейсами Telegram-подарков и присылаю выгодные сделки.\n\n"
        + HELP,
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def cmd_help(m: Message) -> None:
    await m.answer(HELP, parse_mode="HTML")


@router.message(Command("markets"))
async def cmd_markets(m: Message) -> None:
    lines = ["🏪 <b>Статус маркетплейсов</b>\n"]
    for a in ctx().adapters:
        st = await a.health_check()
        icon = {"live": "🟢", "degraded": "🟡", "disabled": "⚫", "not_configured": "⚪"}[st.value]
        line = f"{icon} {a.marketplace.value}: <b>{st.value}</b>"
        if st != SourceStatus.LIVE and a.disabled_reason:
            line += f"\n   <i>{a.disabled_reason[:140]}</i>"
        elif a.latency_ms:
            line += f" ({a.latency_ms:.0f} ms)"
        lines.append(line)
    await m.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("latest"))
async def cmd_latest(m: Message) -> None:
    found = []
    for a in ctx().adapters:
        if a.status == SourceStatus.LIVE:
            try:
                found += await a.fetch_new_listings()
            except Exception as exc:  # noqa: BLE001
                log.warning("latest: %s", exc)
    if not found:
        await m.answer("Нет активных live-источников или новых листингов. См. /markets")
        return
    for l in found[:5]:
        await m.answer(
            format_gift_card_caption(l), parse_mode="HTML", reply_markup=listing_keyboard(l)
        )


@router.message(Command("gift"))
async def cmd_gift(m: Message) -> None:
    args = (m.text or "").split(maxsplit=1)
    if len(args) < 2:
        await m.answer("Использование: /gift Plush Pepe")
        return
    name = args[1].strip()
    found = []
    for a in ctx().adapters:
        if a.status == SourceStatus.LIVE:
            try:
                found += await a.fetch_active_listings(gift_name=name, limit=10)
            except Exception as exc:  # noqa: BLE001
                log.warning("gift: %s", exc)
    if not found:
        await m.answer(f"Листингов «{name}» не найдено на активных источниках.")
        return
    found.sort(key=lambda x: x.price)
    for l in found[:5]:
        await m.answer(
            format_gift_card_caption(l), parse_mode="HTML", reply_markup=listing_keyboard(l)
        )


@router.message(Command("deals", "top"))
async def cmd_deals(m: Message) -> None:
    mode = "ссылкой" if ctx().settings.notification_mode == "link" else "PNG-карточкой и ссылкой"
    await m.answer(
        "Сбор deals идёт в фоне каждые "
        f"{ctx().settings.poll_interval_seconds} c. При выгодной сделке пришлю уведомление с {mode}."
    )


@router.message(Command("filters", "settings"))
async def cmd_settings(m: Message) -> None:
    s = ctx().settings
    await m.answer(
        f"⚙️ <b>Фильтры</b>\n\n"
        f"💰 Мин. прибыль: {s.default_min_profit_ton} TON\n"
        f"📊 Мин. ROI: {s.default_min_roi}%\n"
        f"⏱ Макс. возраст листинга: {s.max_listing_age_seconds} c",
        parse_mode="HTML",
        reply_markup=settings_keyboard(),
    )


@router.message(Command("watchlist"))
async def cmd_watchlist(m: Message) -> None:
    await m.answer("Ваш watchlist пуст. Добавьте подарок кнопкой «В watchlist» под листингом.")


@router.message(Command("history"))
async def cmd_history(m: Message) -> None:
    await m.answer("Укажите листинг через кнопку «История цен» под карточкой.")


@router.callback_query(F.data.startswith("mute:"))
async def cb_mute(c: CallbackQuery) -> None:
    await c.answer("Похожие варианты скрыты 🔕")


@router.callback_query(F.data.startswith("fav:"))
async def cb_fav(c: CallbackQuery) -> None:
    await c.answer("Добавлено в избранное ⭐")


@router.callback_query(F.data.startswith("watch:"))
async def cb_watch(c: CallbackQuery) -> None:
    await c.answer("Добавлено в watchlist 👀")


@router.callback_query(F.data.startswith("hist:"))
async def cb_hist(c: CallbackQuery) -> None:
    await c.answer("История цен появится после накопления снапшотов 📈")


async def send_deal_card(bot: Bot, chat_id: int, deal, card_path=None) -> None:
    """Отправка уведомления: PNG-карточка опционально, ссылка всегда."""
    from aiogram.types import FSInputFile

    if card_path:
        await bot.send_photo(
            chat_id,
            FSInputFile(card_path),
            caption=format_deal(deal)[:1000],
            parse_mode="HTML",
            reply_markup=deal_keyboard(deal),
        )
    else:
        await bot.send_message(
            chat_id, format_deal(deal), parse_mode="HTML", reply_markup=deal_keyboard(deal)
        )


async def build_card_for_deal(deal, out_path) -> object:
    """Оригинальное изображение + рендер карточки по референсу."""
    l = deal.listing
    img = await ctx().images.resolve(
        gift_name=l.gift_name,
        num=l.gift_num,
        custom_emoji_id=l.custom_emoji_id,
        contract=l.ton_contract,
        listing_image_url=l.image_url,
    )
    data = CardData(
        gift_name=l.gift_name,
        gift_num=l.gift_num or 0,
        emoji="🎁",
        model=l.model,
        model_rarity=f"{l.model_rarity_pct}%" if l.model_rarity_pct else "",
        backdrop=l.backdrop,
        backdrop_rarity=f"{l.backdrop_rarity_pct}%" if l.backdrop_rarity_pct else "",
        symbol=l.symbol,
        symbol_rarity=f"{l.symbol_rarity_pct}%" if l.symbol_rarity_pct else "",
        floor_value=str(deal.model_floor.value) if deal.model_floor and deal.model_floor.value else "",
        floor_currency=l.currency.value,
        floor_updated="только что",
        transferable=l.transferable,
        availability_issued=l.availability_issued,
        availability_total=l.availability_total,
        buy_price=f"{deal.buy_price} {l.currency.value}",
        gift_floor=(f"{deal.gift_floor.value} {l.currency.value}" if deal.gift_floor and deal.gift_floor.value else ""),
        model_floor=(f"{deal.model_floor.value} {l.currency.value}" if deal.model_floor and deal.model_floor.value else ""),
        exact_floor=(f"{deal.exact_variant_floor.value} {l.currency.value}" if deal.exact_variant_floor and deal.exact_variant_floor.value else ""),
        profit=(f"+{deal.net_profit} {l.currency.value}" if deal.net_profit else ""),
        roi=(f"+{deal.roi_percent}%" if deal.roi_percent else ""),
        image_path=img,
    )
    return render_card(data, out_path, fonts_dir=ctx().settings.card_font_path.rsplit("/", 1)[0])


__all__ = ["setup_dispatcher", "ctx", "send_deal_card", "build_card_for_deal", "is_worth_alert", "analyze_deal", "Decimal"]
