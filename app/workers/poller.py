"""Фоновый сборщик: poll источников → нормализация → floor → profit → алерты."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from aiogram import Bot

from app.bot.handlers import build_card_for_deal, ctx, send_deal_card
from app.domain.enums import Currency, SourceStatus
from app.domain.models import NormalizedListing
from app.services.floors import exact_variant_floor, gift_floor, model_floor
from app.services.profit import analyze_deal, is_worth_alert

log = logging.getLogger(__name__)


def select_resale_listing(
    target: NormalizedListing, listings: list[NormalizedListing]
) -> NormalizedListing | None:
    """Lowest comparable active ask excluding the listing being evaluated.

    Excluding the candidate matters: using the current model floor as the resale
    price includes the buy listing itself, which makes a positive spread
    impossible for the cheapest listing.
    """
    ton_currencies = {Currency.TON, Currency.GRAM}
    if target.currency not in ton_currencies or not target.model:
        return None

    candidates = [
        listing
        for listing in listings
        if listing.is_active
        and not listing.is_auction
        and listing.listing_id != target.listing_id
        and listing.marketplace == target.marketplace
        and listing.gift_name.casefold() == target.gift_name.casefold()
        and listing.model.casefold() == target.model.casefold()
        and listing.currency in ton_currencies
        and listing.price > 0
    ]
    return min(candidates, key=lambda listing: listing.price, default=None)


class CollectorWorker:
    def __init__(self, bot: Bot, notify_chat_ids: list[int]) -> None:
        self.bot = bot
        self.notify_chat_ids = notify_chat_ids
        self._stop = asyncio.Event()

    async def run(self) -> None:
        c = ctx()
        interval = c.settings.poll_interval_seconds
        max_age = timedelta(seconds=c.settings.max_listing_age_seconds)
        log.info("collector started, interval=%ss", interval)
        if not self.notify_chat_ids:
            log.warning("collector has no notification recipients; set ADMIN_IDS in .env")
        while not self._stop.is_set():
            live_adapters = [a for a in c.adapters if a.status == SourceStatus.LIVE]
            await asyncio.gather(
                *(self._process_adapter_safely(adapter, max_age) for adapter in live_adapters)
            )
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue

    def stop(self) -> None:
        self._stop.set()

    async def _process_adapter_safely(self, adapter, max_age: timedelta) -> None:
        try:
            await self._process_adapter(adapter, max_age)
        except Exception as exc:  # noqa: BLE001 — источник упал, сборщик живёт дальше
            log.error("adapter %s failed: %s", adapter.marketplace.value, exc)

    async def _process_adapter(self, adapter, max_age: timedelta) -> None:
        c = ctx()
        now = datetime.now(timezone.utc)
        listings = await adapter.fetch_new_listings(since=now - max_age)
        if not listings:
            log.info("%s scan: fetched=0", adapter.marketplace.value)
            return

        stats = {
            "fetched": len(listings),
            "fresh": 0,
            "not_active": 0,
            "stale": 0,
            "not_profitable": 0,
            "duplicates": 0,
            "sent": 0,
        }
        pool_cache: dict[str, list[NormalizedListing]] = {}

        # активные листинги того же подарка для floor (из того же источника)
        for l in listings:
            if not l.is_active:
                stats["not_active"] += 1
                continue
            if l.listed_at and datetime.now(timezone.utc) - l.listed_at > max_age:
                stats["stale"] += 1
                continue  # протухший листинг
            stats["fresh"] += 1

            # TON и GRAM взаимозаменяемы 1:1; другие валюты пока не участвуют
            # в оценке, потому что сетевые/трансферные комиссии заданы в TON.
            if l.currency not in (Currency.TON, Currency.GRAM):
                stats["not_profitable"] += 1
                continue

            gift_key = l.gift_name.casefold()
            if gift_key not in pool_cache:
                pool_cache[gift_key] = await adapter.fetch_active_listings(
                    gift_name=l.gift_name, limit=30
                )
            pool = pool_cache[gift_key]
            gf = gift_floor(l, pool)
            mf = model_floor(l, pool)
            ef = exact_variant_floor(l, pool)

            # Для оценки выхода берём ближайший активный ask той же модели,
            # исключая проверяемый листинг. Это ориентир, а не гарантированная продажа.
            resale_listing = select_resale_listing(l, pool)
            sell_price = resale_listing.price if resale_listing else None

            deal = analyze_deal(
                l,
                buy_fee_pct=adapter.get_marketplace_fee(),
                sell_price=sell_price,
                sell_marketplace=resale_listing.marketplace if resale_listing else None,
                sell_fee_pct=Decimal("0.05"),
                deposit_fee_ton=l.deposit_fee_ton,
                withdrawal_fee_ton=l.withdrawal_fee_ton,
                transfer_fee_ton=Decimal(str(c.settings.telegram_transfer_fee_ton)),
                network_fee_ton=Decimal(str(c.settings.network_fee_ton)),
                slippage_reserve_ton=Decimal(str(c.settings.default_slippage_reserve_ton)),
                has_executable_bids=False,
                gift_floor=gf,
                model_floor=mf,
                exact_floor=ef,
            )

            if not is_worth_alert(
                deal,
                min_profit_ton=Decimal(str(c.settings.default_min_profit_ton)),
                min_roi=Decimal(str(c.settings.default_min_roi)),
            ):
                stats["not_profitable"] += 1
                continue
            if c.dedup.is_duplicate(l):
                stats["duplicates"] += 1
                continue

            card = None
            if c.settings.notification_mode.lower() == "card":
                card_path = Path(c.settings.card_cache_dir) / f"deal_{l.marketplace.value}_{l.listing_id}.png"
                try:
                    card = await build_card_for_deal(deal, card_path)
                except Exception as exc:  # noqa: BLE001
                    log.warning("card render failed: %s", exc)

            for chat_id in self.notify_chat_ids:
                try:
                    await send_deal_card(self.bot, chat_id, deal, card)
                    stats["sent"] += 1
                except Exception as exc:  # noqa: BLE001
                    log.error("notify %s failed: %s", chat_id, exc)

        log.info(
            "%s scan: fetched=%d fresh=%d not_active=%d stale=%d "
            "not_profitable=%d duplicates=%d sent=%d",
            adapter.marketplace.value,
            stats["fetched"],
            stats["fresh"],
            stats["not_active"],
            stats["stale"],
            stats["not_profitable"],
            stats["duplicates"],
            stats["sent"],
        )
