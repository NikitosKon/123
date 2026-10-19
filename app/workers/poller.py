"""Фоновый сборщик: poll источников → нормализация → floor → profit → алерты."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from aiogram import Bot

from app.bot.handlers import build_card_for_deal, ctx, send_deal_card
from app.domain.enums import Currency, Marketplace, SourceStatus
from app.domain.models import NormalizedListing, RecentSale
from app.services.floors import exact_variant_floor, gift_floor, model_floor
from app.services.profit import analyze_deal, is_worth_alert
from app.services.valuation import estimate_resale
from app.services.valuation import select_resale_listing as _select_resale_listing

log = logging.getLogger(__name__)


def select_resale_listing(
    target: NormalizedListing, listings: list[NormalizedListing]
) -> NormalizedListing | None:
    """Public helper retained for tests and callers; compares across markets."""
    return _select_resale_listing(target, listings)


class CollectorWorker:
    def __init__(self, bot: Bot, notify_chat_ids: list[int]) -> None:
        self.bot = bot
        self.notify_chat_ids = notify_chat_ids
        self._stop = asyncio.Event()
        self._active_pool_cache: dict[str, tuple[float, list[NormalizedListing], list[Marketplace]]] = {}
        self._sales_cache: dict[str, tuple[float, list[RecentSale]]] = {}
        self._active_locks: dict[str, asyncio.Lock] = {}
        self._sales_locks: dict[str, asyncio.Lock] = {}

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

            pool, sales, compared = await self._market_evidence(l.gift_name, l.model)
            gf = gift_floor(l, pool)
            mf = model_floor(l, pool)
            ef = exact_variant_floor(l, pool)

            # Цена выхода ограничена и активным рынком, и медианой продаж за 30 дней.
            estimate = estimate_resale(l, pool, sales, marketplaces_compared=compared)

            deal = analyze_deal(
                l,
                buy_fee_pct=adapter.get_marketplace_fee(),
                sell_price=estimate.price,
                sell_marketplace=estimate.marketplace,
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
                recent_sales_median=estimate.recent_sales_median,
                recent_sales_count=estimate.recent_sales_count,
                active_comparable_count=estimate.active_comparable_count,
                marketplaces_compared=estimate.marketplaces_compared,
                valuation_basis=estimate.basis,
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

    async def _market_evidence(
        self, gift_name: str, model: str
    ) -> tuple[list[NormalizedListing], list[RecentSale], list[Marketplace]]:
        """Загружает общий рынок и историю сделок с короткими кэшами.

        Активные цены кэшируются 30 секунд, а история сделок — 5 минут, чтобы
        параллельные сканы не создавали шквал запросов площадкам.
        """
        gift_key = gift_name.strip().casefold()
        model_key = model.strip().casefold()
        active_lock = self._active_locks.setdefault(gift_key, asyncio.Lock())
        async with active_lock:
            now = time.monotonic()
            cached = self._active_pool_cache.get(gift_key)
            if cached and cached[0] > now:
                active_listings, compared = cached[1], cached[2]
            else:
                adapters = [a for a in ctx().adapters if a.status == SourceStatus.LIVE]
                responses = await asyncio.gather(
                    *(a.fetch_active_listings(gift_name=gift_name, limit=30) for a in adapters),
                    return_exceptions=True,
                )
                active_listings = []
                compared = []
                for adapter, response in zip(adapters, responses):
                    if isinstance(response, BaseException):
                        log.debug("active price lookup failed on %s: %s", adapter.marketplace.value, response)
                        continue
                    active_listings.extend(response)
                    compared.append(adapter.marketplace)
                self._active_pool_cache[gift_key] = (
                    time.monotonic() + 30,
                    active_listings,
                    compared,
                )

        if not model_key:
            return active_listings, [], compared

        evidence_key = f"{gift_key}|{model_key}"
        sales_lock = self._sales_locks.setdefault(evidence_key, asyncio.Lock())
        async with sales_lock:
            cached_sales = self._sales_cache.get(evidence_key)
            if cached_sales and cached_sales[0] > time.monotonic():
                return active_listings, cached_sales[1], compared

            adapters = [a for a in ctx().adapters if a.status == SourceStatus.LIVE]
            since = datetime.now(timezone.utc) - timedelta(days=30)
            sales_responses = await asyncio.gather(
                *(
                    a.fetch_recent_sales(gift_name, model, since, limit=50)
                    for a in adapters
                ),
                return_exceptions=True,
            )
            sales: list[RecentSale] = []
            seen: set[tuple[str, str, str, str]] = set()
            for adapter, sales_response in zip(adapters, sales_responses):
                if isinstance(sales_response, BaseException):
                    log.debug("sales lookup failed on %s: %s", adapter.marketplace.value, sales_response)
                    continue
                for sale in sales_response:
                    signature = (
                        sale.marketplace.value,
                        sale.listing_id,
                        str(sale.sold_at),
                        str(sale.price),
                    )
                    if signature not in seen:
                        seen.add(signature)
                        sales.append(sale)
            self._sales_cache[evidence_key] = (time.monotonic() + 300, sales)
            return active_listings, sales, compared
