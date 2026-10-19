"""Domain schemas. Все денежные значения — Decimal, никаких float."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain.enums import Confidence, Currency, Marketplace
from app.domain.traits import normalize_backdrop


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class NormalizedListing(BaseModel):
    """Единый нормализованный вид объявления со всех маркетплейсов."""

    marketplace: Marketplace
    listing_id: str
    url: str = ""

    gift_name: str
    gift_type_id: str = ""
    model: str = ""
    model_rarity_pct: Decimal | None = None
    backdrop: str = ""
    backdrop_rarity_pct: Decimal | None = None
    symbol: str = ""
    symbol_rarity_pct: Decimal | None = None

    gift_num: int | None = None
    telegram_gift_id: str = ""
    custom_emoji_id: str = ""
    ton_contract: str = ""
    ton_token_id: str = ""

    image_url: str = ""
    animation_url: str = ""

    price: Decimal
    currency: Currency = Currency.TON
    price_ton: Decimal | None = None
    price_usd: Decimal | None = None

    marketplace_fee_pct: Decimal = Decimal("0")
    network_fee_ton: Decimal = Decimal("0")
    withdrawal_fee_ton: Decimal = Decimal("0")
    deposit_fee_ton: Decimal = Decimal("0")

    availability_issued: int | None = None
    availability_total: int | None = None
    transferable: bool | None = None

    listed_at: datetime | None = None
    updated_at: datetime | None = None
    fetched_at: datetime = Field(default_factory=utcnow)
    is_active: bool = True
    is_auction: bool = False

    raw: dict[str, Any] = Field(default_factory=dict, exclude=True)

    @model_validator(mode="before")
    @classmethod
    def normalize_backdrop_trait(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values
        normalized = dict(values)
        backdrop, rarity = normalize_backdrop(
            normalized.get("backdrop", ""), normalized.get("backdrop_rarity_pct")
        )
        normalized["backdrop"] = backdrop
        if normalized.get("backdrop_rarity_pct") is None and rarity is not None:
            normalized["backdrop_rarity_pct"] = rarity
        return normalized

    @property
    def variant_fingerprint(self) -> str:
        return f"{self.gift_name}|{self.model}|{self.backdrop}|{self.symbol}".lower()

    @property
    def dedup_fingerprint(self) -> str:
        return (
            f"{self.marketplace.value}|{self.listing_id}|{self.price}|{self.variant_fingerprint}"
        )


class RecentSale(BaseModel):
    """Нормализованная подтверждённая продажа для оценки цены выхода."""

    marketplace: Marketplace
    listing_id: str = ""
    gift_name: str
    model: str
    backdrop: str = ""
    gift_num: int | None = None
    price: Decimal
    currency: Currency = Currency.TON
    sold_at: datetime
    url: str = ""

    @field_validator("backdrop", mode="before")
    @classmethod
    def normalize_backdrop_trait(cls, value: Any) -> str:
        return normalize_backdrop(value)[0]


class FloorQuote(BaseModel):
    """Один из типов floor с метаданными."""

    kind: str  # gift_floor | model_floor | exact_variant_floor | global_floor
    value: Decimal | None = None
    currency: Currency = Currency.TON
    marketplace: Marketplace | None = None
    url: str = ""
    listings_count: int = 0
    updated_at: datetime = Field(default_factory=utcnow)
    confidence: Confidence = Confidence.MEDIUM

    @property
    def age_seconds(self) -> float:
        return (utcnow() - self.updated_at).total_seconds()


class DealAnalysis(BaseModel):
    """Расчёт потенциальной прибыли по объявлению."""

    listing: NormalizedListing
    buy_price: Decimal
    buy_marketplace: Marketplace
    sell_price: Decimal | None = None
    sell_marketplace: Marketplace | None = None
    recent_sales_median: Decimal | None = None
    recent_sales_count: int = 0
    active_comparable_count: int = 0
    marketplaces_compared: list[Marketplace] = Field(default_factory=list)
    valuation_basis: str = ""

    total_costs: Decimal = Decimal("0")
    gross_profit: Decimal | None = None
    net_profit: Decimal | None = None
    roi_percent: Decimal | None = None

    gift_floor: FloorQuote | None = None
    model_floor: FloorQuote | None = None
    backdrop_floor: FloorQuote | None = None
    exact_variant_floor: FloorQuote | None = None
    backdrop_sales_median: Decimal | None = None
    backdrop_sales_count: int = 0
    backdrop_comparable_count: int = 0

    confidence: Confidence = Confidence.LOW
    status: str = "estimated"  # прибыль всегда estimated, если нет исполнимых bids
    updated_at: datetime = Field(default_factory=utcnow)
