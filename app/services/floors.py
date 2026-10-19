"""Расчёт floor: gift / model / exact variant / global."""
from __future__ import annotations

from decimal import Decimal

from app.domain.enums import Confidence, Currency
from app.domain.models import FloorQuote, NormalizedListing


def _min_listing(listings: list[NormalizedListing]) -> NormalizedListing | None:
    active = [l for l in listings if l.is_active and l.price > 0]
    return min(active, key=lambda l: l.price, default=None)


def _quote(kind: str, pool: list[NormalizedListing]) -> FloorQuote:
    best = _min_listing(pool)
    if best is None:
        return FloorQuote(kind=kind, value=None, listings_count=len(pool), confidence=Confidence.LOW)
    confidence = Confidence.LOW_CONFIDENCE if len(pool) == 1 else (
        Confidence.HIGH if len(pool) >= 5 else Confidence.MEDIUM
    )
    return FloorQuote(
        kind=kind,
        value=best.price,
        currency=best.currency,
        marketplace=best.marketplace,
        url=best.url,
        listings_count=len(pool),
        confidence=confidence,
    )


def _comparable_currency(target: NormalizedListing, listing: NormalizedListing) -> bool:
    ton_currencies = {Currency.TON, Currency.GRAM}
    if target.currency in ton_currencies:
        return listing.currency in ton_currencies
    return target.currency == listing.currency


def gift_floor(target: NormalizedListing, all_listings: list[NormalizedListing]) -> FloorQuote:
    """Минимальная цена среди всех вариантов того же базового подарка."""
    pool = [
        l for l in all_listings
        if l.gift_name.casefold() == target.gift_name.casefold()
        and _comparable_currency(target, l)
    ]
    return _quote("gift_floor", pool)


def model_floor(target: NormalizedListing, all_listings: list[NormalizedListing]) -> FloorQuote:
    """Минимальная цена той же модели (любой backdrop/symbol)."""
    pool = [
        l
        for l in all_listings
        if l.gift_name.casefold() == target.gift_name.casefold()
        and l.model.casefold() == target.model.casefold()
        and _comparable_currency(target, l)
    ]
    return _quote("model_floor", pool)


def backdrop_floor(target: NormalizedListing, all_listings: list[NormalizedListing]) -> FloorQuote:
    """Minimum active listing for the same gift, model, and backdrop."""
    backdrop_key = target.backdrop.strip().casefold()
    pool = [
        listing
        for listing in all_listings
        if backdrop_key
        and listing.is_active
        and not listing.is_auction
        and listing.gift_name.casefold() == target.gift_name.casefold()
        and listing.model.casefold() == target.model.casefold()
        and listing.backdrop.strip().casefold() == backdrop_key
        and _comparable_currency(target, listing)
    ]
    return _quote("backdrop_floor", pool)


def exact_variant_floor(
    target: NormalizedListing, all_listings: list[NormalizedListing]
) -> FloorQuote:
    """Минимальная цена точного варианта (gift + model + backdrop + symbol)."""
    pool = [l for l in all_listings
            if l.variant_fingerprint == target.variant_fingerprint
            and _comparable_currency(target, l)]
    return _quote("exact_variant_floor", pool)


def global_floor(target: NormalizedListing, all_listings: list[NormalizedListing]) -> FloorQuote:
    """Минимум по модели среди ВСЕХ маркетплейсов (цены уже нормализованы в TON)."""
    pool = [
        l
        for l in all_listings
        if l.gift_name.lower() == target.gift_name.lower()
        and l.model.lower() == target.model.lower()
        and l.price_ton is not None
    ]
    if not pool:
        return FloorQuote(kind="global_floor", value=None, confidence=Confidence.LOW)
    best = min(pool, key=lambda l: l.price_ton or Decimal("Infinity"))
    return FloorQuote(
        kind="global_floor",
        value=best.price_ton,
        currency=best.currency,
        marketplace=best.marketplace,
        url=best.url,
        listings_count=len(pool),
        confidence=Confidence.LOW_CONFIDENCE if len(pool) == 1 else Confidence.MEDIUM,
    )
