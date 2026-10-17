"""Фоновый сборщик: poll источников → нормализация → floor → profit → алерты."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from aiogram import Bot

from app.bot.handlers import build_card_for_deal, ctx, send_deal_card
from app.domain.enums import SourceStatus
from app.services.floors import exact_variant_floor, gift_floor, model_floor
from app.services.profit import analyze_deal, is_worth_alert

log = logging.getLogger(__name__)


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
            for adapter in c.adapters:
                if adapter.status != SourceStatus.LIVE:
                    continue
                try:
                    await self._process_adapter(adapter, max_age)
                except Exception as exc:  # noqa: BLE001 — источник упал, сборщик живёт дальше
                    log.error("adapter %s failed: %s", adapter.marketplace.value, exc)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue

    def stop(self) -> None:
        self._stop.set()

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

        # активные листинги того же подарка для floor (из того же источника)
        for l in listings:
            if not l.is_active:
                stats["not_active"] += 1
                continue
            if l.listed_at and datetime.now(timezone.utc) - l.listed_at > max_age:
                stats["stale"] += 1
                continue  # протухший листинг
            stats["fresh"] += 1

            pool = await adapter.fetch_active_listings(gift_name=l.gift_name, limit=30)
            gf = gift_floor(l, pool)
            mf = model_floor(l, pool)
            ef = exact_variant_floor(l, pool)

            # консервативная цена выхода: model floor (не самая дорогая цена)
            sell_price = mf.value if mf and mf.value else None

            deal = analyze_deal(
                l,
                buy_fee_pct=adapter.get_marketplace_fee(),
                sell_price=sell_price,
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
