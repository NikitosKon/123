"""Репозиторий: upsert листингов, выборки для floor, запись алертов."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import NormalizedListing
from app.storage.models import Gift, GiftVariant, Listing, PriceSnapshot


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def upsert_listing(session: AsyncSession, l: NormalizedListing) -> Listing:
    variant_id = None
    gift = (
        await session.execute(select(Gift).where(Gift.name == l.gift_name))
    ).scalar_one_or_none()
    if gift is None:
        gift = Gift(name=l.gift_name, total_issued=l.availability_total)
        session.add(gift)
        await session.flush()
    if l.variant_fingerprint.strip("|"):
        variant = (
            await session.execute(
                select(GiftVariant).where(GiftVariant.fingerprint == l.variant_fingerprint)
            )
        ).scalar_one_or_none()
        if variant is None:
            variant = GiftVariant(
                gift_id=gift.id,
                model=l.model,
                model_rarity_pct=l.model_rarity_pct,
                backdrop=l.backdrop,
                backdrop_rarity_pct=l.backdrop_rarity_pct,
                symbol=l.symbol,
                symbol_rarity_pct=l.symbol_rarity_pct,
                fingerprint=l.variant_fingerprint,
            )
            session.add(variant)
            await session.flush()
        variant_id = variant.id

    row = (
        await session.execute(
            select(Listing).where(
                Listing.marketplace == l.marketplace.value,
                Listing.listing_id == l.listing_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = Listing(
            marketplace=l.marketplace.value,
            listing_id=l.listing_id,
            url=l.url,
            variant_id=variant_id,
            gift_num=l.gift_num,
            telegram_gift_id=l.telegram_gift_id,
            ton_contract=l.ton_contract,
            price=l.price,
            currency=l.currency.value,
            price_ton=l.price_ton,
            price_usd=l.price_usd,
            fee_pct=l.marketplace_fee_pct,
            is_active=l.is_active,
            listed_at=l.listed_at,
            fetched_at=l.fetched_at,
            raw=l.raw,
            dedup_fingerprint=l.dedup_fingerprint,
        )
        session.add(row)
    else:
        if row.price != l.price:
            session.add(PriceSnapshot(listing_pk=row.id, price=l.price))
        row.price = l.price
        row.is_active = l.is_active
        row.updated_at = _utcnow()
        row.raw = l.raw
        row.dedup_fingerprint = l.dedup_fingerprint
    await session.commit()
    return row


async def active_listings_for_gift(session: AsyncSession, gift_name: str) -> list[Listing]:
    q = (
        select(Listing)
        .join(GiftVariant, Listing.variant_id == GiftVariant.id, isouter=True)
        .join(Gift, GiftVariant.gift_id == Gift.id, isouter=True)
        .where(Gift.name == gift_name, Listing.is_active.is_(True))
    )
    return list((await session.execute(q)).scalars())
