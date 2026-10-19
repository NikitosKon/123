"""Persistent recommendations and their later, confirmed sale outcomes."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from app.bot.formatters import purchase_url, telegram_gift_url
from app.domain.models import DealAnalysis, RecentSale
from app.services.dedup import fingerprint
from app.storage.db import get_session_factory
from app.storage.models import Recommendation


def classify_sale(sale: RecentSale, recommendation: Recommendation) -> str | None:
    """Match a later sale to the recommended collectible and classify the price move."""
    if sale.gift_num is None or sale.gift_num != recommendation.gift_num:
        return None
    if sale.gift_name.casefold() != recommendation.gift_name.casefold():
        return None
    if sale.model.casefold() != recommendation.model.casefold():
        return None
    recommended_at = recommendation.created_at
    if recommended_at.tzinfo is None:
        recommended_at = recommended_at.replace(tzinfo=timezone.utc)
    sold_at = sale.sold_at
    if sold_at.tzinfo is None:
        sold_at = sold_at.replace(tzinfo=timezone.utc)
    if sold_at <= recommended_at:
        return None
    return "flipped" if sale.price > recommendation.buy_price else "sold"


async def record_recommendation(deal: DealAnalysis, recipient_ids: list[int]) -> Recommendation | None:
    """Store only identifiable Telegram collectibles, so later sales can be matched."""
    listing = deal.listing
    if listing.gift_num is None or not listing.model or not recipient_ids:
        return None

    raw = listing.raw if isinstance(listing.raw, dict) else {}
    raw_sale = raw.get("sale")
    sale = raw_sale if isinstance(raw_sale, dict) else {}
    kind = str(raw.get("kind") or "")
    is_offchain = (
        kind in {"OffchainNft", "OffchainSticker"}
        or str(sale.get("contractType") or "").casefold() == "offchain"
    )
    collection_address = str(raw.get("collectionAddress") or listing.ton_contract or "")
    record_key = fingerprint(listing)

    async with get_session_factory()() as session:
        row = await session.scalar(
            select(Recommendation).where(Recommendation.fingerprint == record_key)
        )
        if row is None:
            row = Recommendation(
                fingerprint=record_key,
                marketplace=listing.marketplace.value,
                listing_id=listing.listing_id,
                gift_name=listing.gift_name,
                gift_num=listing.gift_num,
                model=listing.model,
                backdrop=listing.backdrop,
                symbol=listing.symbol,
                buy_price=deal.buy_price,
                currency=listing.currency.value,
                buy_url=purchase_url(listing),
                telegram_url=telegram_gift_url(listing),
                collection_address=collection_address,
                collection_offchain=is_offchain,
                recipient_ids=sorted(set(recipient_ids)),
                status="watching",
            )
            session.add(row)
        else:
            row.recipient_ids = sorted(set((row.recipient_ids or []) + recipient_ids))
            if collection_address and not row.collection_address:
                row.collection_address = collection_address
                row.collection_offchain = is_offchain
        await session.commit()
        await session.refresh(row)
        return row


async def pending_recommendations(limit: int = 500) -> list[Recommendation]:
    async with get_session_factory()() as session:
        result = await session.scalars(
            select(Recommendation)
            .where(Recommendation.status == "watching")
            .order_by(Recommendation.created_at.asc())
            .limit(limit)
        )
        return list(result)


async def pending_outcome_notifications(limit: int = 100) -> list[Recommendation]:
    async with get_session_factory()() as session:
        result = await session.scalars(
            select(Recommendation)
            .where(
                Recommendation.status.in_(("sold", "flipped")),
                Recommendation.outcome_notified_at.is_(None),
            )
            .order_by(Recommendation.sale_at.asc())
            .limit(limit)
        )
        return list(result)


async def record_sale_outcome(
    recommendation_id: int, sale: RecentSale, status: str
) -> Recommendation | None:
    async with get_session_factory()() as session:
        row = await session.get(Recommendation, recommendation_id)
        if row is None or row.status != "watching":
            return row
        row.status = status
        row.sale_price = sale.price
        row.sale_marketplace = sale.marketplace.value
        row.sale_at = sale.sold_at
        row.sale_url = sale.url
        await session.commit()
        await session.refresh(row)
        return row


async def mark_recipient_notified(recommendation_id: int, recipient_id: int) -> None:
    async with get_session_factory()() as session:
        row = await session.get(Recommendation, recommendation_id)
        if row is None:
            return
        notified = set(row.notified_recipient_ids or [])
        notified.add(recipient_id)
        row.notified_recipient_ids = sorted(notified)
        if set(row.recipient_ids or []).issubset(notified):
            row.outcome_notified_at = datetime.now(timezone.utc)
        await session.commit()


async def mark_empty_outcome_notification(recommendation_id: int) -> None:
    async with get_session_factory()() as session:
        row = await session.get(Recommendation, recommendation_id)
        if row is not None:
            row.outcome_notified_at = datetime.now(timezone.utc)
            await session.commit()


async def recent_outcomes(limit: int = 10) -> list[Recommendation]:
    async with get_session_factory()() as session:
        result = await session.scalars(
            select(Recommendation)
            .where(Recommendation.status.in_(("sold", "flipped")))
            .order_by(Recommendation.sale_at.desc())
            .limit(limit)
        )
        return list(result)


def sale_delta(sale_price: Decimal, buy_price: Decimal) -> Decimal:
    return sale_price - buy_price
