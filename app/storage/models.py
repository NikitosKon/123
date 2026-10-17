"""ORM-модели. Деньги — Numeric(20, 8), никогда Float."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Index, Numeric, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class MarketplaceRow(Base):
    __tablename__ = "marketplaces"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(32), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="not_configured")
    fee_pct: Mapped[Decimal] = mapped_column(Numeric(6, 3), default=0)
    last_ok_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Gift(Base):
    __tablename__ = "gifts"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    type_id: Mapped[str] = mapped_column(String(64), default="")
    total_issued: Mapped[int | None] = mapped_column(nullable=True)

    __table_args__ = (Index("ix_gifts_name", "name"),)


class GiftVariant(Base):
    __tablename__ = "gift_variants"
    id: Mapped[int] = mapped_column(primary_key=True)
    gift_id: Mapped[int] = mapped_column(index=True)
    model: Mapped[str] = mapped_column(String(128), default="", index=True)
    model_rarity_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    backdrop: Mapped[str] = mapped_column(String(128), default="", index=True)
    backdrop_rarity_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    symbol: Mapped[str] = mapped_column(String(128), default="", index=True)
    symbol_rarity_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(256), unique=True, index=True)


class Listing(Base):
    __tablename__ = "listings"
    id: Mapped[int] = mapped_column(primary_key=True)
    marketplace: Mapped[str] = mapped_column(String(32), index=True)
    listing_id: Mapped[str] = mapped_column(String(128), index=True)
    url: Mapped[str] = mapped_column(Text, default="")
    variant_id: Mapped[int | None] = mapped_column(index=True, nullable=True)
    gift_num: Mapped[int | None] = mapped_column(nullable=True)
    telegram_gift_id: Mapped[str] = mapped_column(String(64), default="")
    ton_contract: Mapped[str] = mapped_column(String(80), default="")
    price: Mapped[Decimal] = mapped_column(Numeric(20, 8), index=True)
    currency: Mapped[str] = mapped_column(String(8), default="TON")
    price_ton: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    price_usd: Mapped[Decimal | None] = mapped_column(Numeric(20, 2), nullable=True)
    fee_pct: Mapped[Decimal] = mapped_column(Numeric(6, 3), default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    listed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    raw: Mapped[dict] = mapped_column(JSON, default=dict)
    dedup_fingerprint: Mapped[str] = mapped_column(String(96), index=True, default="")

    __table_args__ = (
        Index("ix_listings_mp_variant_active", "marketplace", "variant_id", "is_active"),
        Index("ix_listings_created", "listed_at"),
    )


class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    listing_pk: Mapped[int] = mapped_column(index=True)
    price: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Sale(Base):
    __tablename__ = "sales"
    id: Mapped[int] = mapped_column(primary_key=True)
    marketplace: Mapped[str] = mapped_column(String(32), index=True)
    variant_id: Mapped[int | None] = mapped_column(index=True, nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    currency: Mapped[str] = mapped_column(String(8), default="TON")
    sold_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str] = mapped_column(String(64), default="")
    display_currency: Mapped[str] = mapped_column(String(8), default="TON")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UserFilter(Base):
    __tablename__ = "user_filters"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(index=True)
    min_profit_ton: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=0.2)
    min_roi: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=10)
    max_price_ton: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    collections: Mapped[list] = mapped_column(JSON, default=list)
    models: Mapped[list] = mapped_column(JSON, default=list)
    marketplaces: Mapped[list] = mapped_column(JSON, default=list)
    min_confirmations: Mapped[int] = mapped_column(default=1)
    excluded_gifts: Mapped[list] = mapped_column(JSON, default=list)
    cooldown_seconds: Mapped[int] = mapped_column(default=3600)


class Watchlist(Base):
    __tablename__ = "watchlists"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(index=True)
    gift_name: Mapped[str] = mapped_column(String(128), index=True)
    model: Mapped[str] = mapped_column(String(128), default="")
    max_price_ton: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(index=True)
    listing_pk: Mapped[int] = mapped_column(index=True)
    fingerprint: Mapped[str] = mapped_column(String(96), index=True)
    net_profit: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    roi: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SourceHealth(Base):
    __tablename__ = "source_health"
    id: Mapped[int] = mapped_column(primary_key=True)
    marketplace: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(16))
    latency_ms: Mapped[float | None] = mapped_column(nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
