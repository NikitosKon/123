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
    backdrop_floor: Decimal | None = None
    backdrop_comparable_count: int = 0
    backdrop_sales_median: Decimal | None = None
    backdrop_sales_count: int = 0


def select_resale_listing(
    target: NormalizedListing, listings: list[NormalizedListing]
) -> NormalizedListing | None:
    """Самый дешёвый активный листинг той же модели и, если задан, фона."""
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
        and _same_backdrop(target.backdrop, listing.backdrop)
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
    """Оценивает выход по сопоставимому фону, модели и 30-дневным продажам.

    Если продаж точного фона нет, использует консервативную оценку модели.
    Запрашиваемая цена редкого фона не создаёт премию без подтверждения продажей.
    """
    now = as_of or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    cutoff = now - RECENT_SALES_WINDOW

    model_listings = [
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
    best_model_listing = min(model_listings, key=lambda item: item.price, default=None)

    model_sales = [
        sale
        for sale in sales
        if sale.gift_name.casefold() == target.gift_name.casefold()
        and sale.model.casefold() == target.model.casefold()
        and sale.currency in TON_CURRENCIES
        and sale.price > 0
        and cutoff <= _as_utc(sale.sold_at) <= now
    ] if target.model and target.currency in TON_CURRENCIES else []
    model_sales.sort(key=lambda sale: _as_utc(sale.sold_at), reverse=True)
    model_sales = model_sales[:MAX_RECENT_SALES]
    model_sales_median = median([sale.price for sale in model_sales]) if model_sales else None

    backdrop_key = target.backdrop.strip().casefold()
    backdrop_listings = [
        listing for listing in model_listings
        if backdrop_key and listing.backdrop.strip().casefold() == backdrop_key
    ]
    best_backdrop_listing = min(backdrop_listings, key=lambda item: item.price, default=None)
    backdrop_sales = [
        sale for sale in model_sales
        if backdrop_key and sale.backdrop.strip().casefold() == backdrop_key
    ]
    backdrop_sales_median = (
        median([sale.price for sale in backdrop_sales]) if backdrop_sales else None
    )

    # Generic model data remains a conservative fallback. A rare background's
    # single high asking price cannot create a fictional premium: a premium is
    # accepted only when actual sales for that same background support it.
    marketplace: Marketplace | None = None
    model_marketplace: Marketplace | None
    model_price: Decimal | None
    model_basis: str
    if best_model_listing and model_sales_median is not None:
        if best_model_listing.price <= model_sales_median:
            model_price = best_model_listing.price
            model_marketplace = best_model_listing.marketplace
        else:
            model_price = model_sales_median
            middle_sale = _representative_sale(model_sales)
            model_marketplace = middle_sale.marketplace if len(model_sales) % 2 else None
        model_basis = "минимум активных листингов и медиана продаж"
    elif best_model_listing:
        model_price = best_model_listing.price
        model_marketplace = best_model_listing.marketplace
        model_basis = "минимум активных сопоставимых листингов"
    elif model_sales_median is not None:
        model_price = model_sales_median
        middle_sale = _representative_sale(model_sales)
        model_marketplace = middle_sale.marketplace if len(model_sales) % 2 else None
        model_basis = "медиана фактических продаж"
    else:
        model_price = None
        model_marketplace = None
        model_basis = "нет сопоставимых данных"

    if not backdrop_key:
        price = model_price
        marketplace = model_marketplace
        basis = model_basis
        comparable_count = len(model_listings)
        sales_median = model_sales_median
        comparable_sales = model_sales
    elif backdrop_sales_median is not None:
        if best_backdrop_listing and best_backdrop_listing.price <= backdrop_sales_median:
            price = best_backdrop_listing.price
            marketplace = best_backdrop_listing.marketplace
        else:
            price = backdrop_sales_median
            middle_sale = _representative_sale(backdrop_sales)
            marketplace = middle_sale.marketplace if len(backdrop_sales) % 2 else None
        basis = "листинги и продажи того же фона"
        comparable_count = len(backdrop_listings)
        sales_median = backdrop_sales_median
        comparable_sales = backdrop_sales
    elif model_price is not None:
        if best_backdrop_listing and best_backdrop_listing.price < model_price:
            price = best_backdrop_listing.price
            marketplace = best_backdrop_listing.marketplace
            basis = "floor фона; премия не подтверждена продажами"
        else:
            price = model_price
            marketplace = model_marketplace
            basis = "оценка по модели; нет продаж этого фона"
        comparable_count = len(backdrop_listings)
        sales_median = model_sales_median
        comparable_sales = model_sales
    else:
        price = None
        marketplace = None
        basis = "нет данных для оценки этого фона"
        comparable_count = len(backdrop_listings)
        sales_median = None
        comparable_sales = []

    compared = list(dict.fromkeys(marketplaces_compared or []))
    return ResaleEstimate(
        price=price,
        marketplace=marketplace,
        basis=basis,
        active_comparable_count=comparable_count,
        recent_sales_median=sales_median,
        recent_sales_count=len(comparable_sales),
        marketplaces_compared=compared,
        backdrop_floor=(best_backdrop_listing.price if best_backdrop_listing else None),
        backdrop_comparable_count=len(backdrop_listings),
        backdrop_sales_median=backdrop_sales_median,
        backdrop_sales_count=len(backdrop_sales),
    )


def _same_backdrop(target_backdrop: str, comparable_backdrop: str) -> bool:
    """Use same-background resale listings when the target has a backdrop."""
    return (
        not target_backdrop.strip()
        or comparable_backdrop.strip().casefold() == target_backdrop.strip().casefold()
    )


def _representative_sale(sales: list[RecentSale]) -> RecentSale:
    """Representative sale at the lower median price, independent of recency order."""
    return sorted(sales, key=lambda sale: sale.price)[(len(sales) - 1) // 2]


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
