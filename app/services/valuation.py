"""Консервативная оценка цены выхода по листингам и завершённым продажам."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from statistics import median

from app.domain.enums import Currency, Marketplace
from app.domain.models import NormalizedListing, RecentSale

RECENT_SALES_WINDOW = timedelta(days=30)
MAX_RECENT_SALES = 10
TON_CURRENCIES = {Currency.TON, Currency.GRAM}


@dataclass(frozen=True)
class ResaleEstimate:
    price: Decimal | None
    marketplace: Marketplace | None
    basis: str
    active_comparable_count: int
    recent_sales_median: Decimal | None
    recent_sales_count: int
    marketplaces_compared: list[Marketplace]


def select_resale_listing(
    target: NormalizedListing, listings: list[NormalizedListing]
) -> NormalizedListing | None:
    """Самый дешёвый активный листинг той же модели на любой площадке."""
    if target.currency not in TON_CURRENCIES or not target.model:
        return None

    candidates = [
        listing
        for listing in listings
        if listing.is_active
        and not listing.is_auction
        and not (
            listing.marketplace == target.marketplace
            and listing.listing_id == target.listing_id
        )
        and listing.gift_name.casefold() == target.gift_name.casefold()
        and listing.model.casefold() == target.model.casefold()
        and listing.currency in TON_CURRENCIES
        and listing.price > 0
    ]
    return min(candidates, key=lambda listing: listing.price, default=None)


def estimate_resale(
    target: NormalizedListing,
    listings: list[NormalizedListing],
    sales: list[RecentSale],
    *,
    marketplaces_compared: list[Marketplace] | None = None,
    as_of: datetime | None = None,
) -> ResaleEstimate:
    """Берёт меньшую из cross-market ask floor и 30-дневной медианы продаж.

    Если доступен только один тип данных, использует его и отражает это в
    `basis`. Продажи с другой моделью, валютой или за пределами окна исключаются.
    """
    now = as_of or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    cutoff = now - RECENT_SALES_WINDOW

    comparable_listings = [
        listing
        for listing in listings
        if listing.is_active
        and not listing.is_auction
        and not (
            listing.marketplace == target.marketplace
            and listing.listing_id == target.listing_id
        )
        and listing.gift_name.casefold() == target.gift_name.casefold()
        and listing.model.casefold() == target.model.casefold()
        and listing.currency in TON_CURRENCIES
        and listing.price > 0
    ] if target.model and target.currency in TON_CURRENCIES else []
    best_listing = min(comparable_listings, key=lambda item: item.price, default=None)
    marketplace: Marketplace | None = None

    comparable_sales = [
        sale
        for sale in sales
        if sale.gift_name.casefold() == target.gift_name.casefold()
        and sale.model.casefold() == target.model.casefold()
        and sale.currency in TON_CURRENCIES
        and sale.price > 0
        and cutoff <= _as_utc(sale.sold_at) <= now
    ] if target.model and target.currency in TON_CURRENCIES else []
    comparable_sales.sort(key=lambda sale: _as_utc(sale.sold_at), reverse=True)
    comparable_sales = comparable_sales[:MAX_RECENT_SALES]
    sales_median = median([sale.price for sale in comparable_sales]) if comparable_sales else None

    if best_listing and sales_median is not None:
        if best_listing.price <= sales_median:
            price = best_listing.price
            marketplace = best_listing.marketplace
        else:
            price = sales_median
            # Для чётного числа продаж медиана может не соответствовать одной площадке.
            middle_sale = comparable_sales[(len(comparable_sales) - 1) // 2]
            marketplace = middle_sale.marketplace if len(comparable_sales) % 2 else None
        basis = "минимум активных листингов и медиана продаж"
    elif best_listing:
        price = best_listing.price
        marketplace = best_listing.marketplace
        basis = "минимум активных сопоставимых листингов"
    elif sales_median is not None:
        price = sales_median
        middle_sale = comparable_sales[(len(comparable_sales) - 1) // 2]
        marketplace = middle_sale.marketplace if len(comparable_sales) % 2 else None
        basis = "медиана фактических продаж"
    else:
        price = None
        marketplace = None
        basis = "нет сопоставимых данных"

    compared = list(dict.fromkeys(marketplaces_compared or []))
    return ResaleEstimate(
        price=price,
        marketplace=marketplace,
        basis=basis,
        active_comparable_count=len(comparable_listings),
        recent_sales_median=sales_median,
        recent_sales_count=len(comparable_sales),
        marketplaces_compared=compared,
    )


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
