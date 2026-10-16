"""Расчёт потенциальной прибыли. Только Decimal.

entry_cost    = buy_price + buyer_fee + deposit_fee + transfer_fee + network_fee + slippage
exit_proceeds = sell_price - seller_fee - withdrawal_fee - network_fee
net_profit    = exit_proceeds - entry_cost
roi_percent   = net_profit / entry_cost * 100
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from app.domain.enums import Confidence
from app.domain.models import DealAnalysis, FloorQuote, NormalizedListing

CENT = Decimal("0.01")


def q2(v: Decimal) -> Decimal:
    return v.quantize(CENT, rounding=ROUND_HALF_UP)


def analyze_deal(
    listing: NormalizedListing,
    *,
    buy_fee_pct: Decimal,
    sell_price: Decimal | None,
    sell_fee_pct: Decimal = Decimal("0"),
    deposit_fee_ton: Decimal = Decimal("0"),
    withdrawal_fee_ton: Decimal = Decimal("0"),
    transfer_fee_ton: Decimal = Decimal("0"),
    network_fee_ton: Decimal = Decimal("0"),
    slippage_reserve_ton: Decimal = Decimal("0"),
    has_executable_bids: bool = False,
    gift_floor: FloorQuote | None = None,
    model_floor: FloorQuote | None = None,
    exact_floor: FloorQuote | None = None,
) -> DealAnalysis:
    buy_price = listing.price
    buyer_fee = buy_price * buy_fee_pct
    entry_cost = (
        buy_price + buyer_fee + deposit_fee_ton + transfer_fee_ton + network_fee_ton + slippage_reserve_ton
    )

    net_profit: Decimal | None = None
    roi: Decimal | None = None
    gross: Decimal | None = None
    status = "estimated"

    if sell_price is not None and entry_cost > 0:
        seller_fee = sell_price * sell_fee_pct
        exit_proceeds = sell_price - seller_fee - withdrawal_fee_ton - network_fee_ton
        gross = sell_price - buy_price
        net_profit = exit_proceeds - entry_cost
        roi = net_profit / entry_cost * Decimal("100")
        if has_executable_bids:
            status = "confirmed"  # есть реальные buy orders — цена выхода исполнима
    total_costs = entry_cost - buy_price

    confidence = Confidence.LOW
    if status == "confirmed":
        confidence = Confidence.HIGH
    elif model_floor and model_floor.listings_count >= 3:
        confidence = Confidence.MEDIUM

    return DealAnalysis(
        listing=listing,
        buy_price=q2(buy_price),
        buy_marketplace=listing.marketplace,
        sell_price=q2(sell_price) if sell_price is not None else None,
        sell_marketplace=(model_floor.marketplace if model_floor else None),
        total_costs=q2(total_costs),
        gross_profit=q2(gross) if gross is not None else None,
        net_profit=q2(net_profit) if net_profit is not None else None,
        roi_percent=q2(roi) if roi is not None else None,
        gift_floor=gift_floor,
        model_floor=model_floor,
        exact_variant_floor=exact_floor,
        confidence=confidence,
        status=status,
    )


def is_worth_alert(
    deal: DealAnalysis, *, min_profit_ton: Decimal, min_roi: Decimal
) -> bool:
    """Уведомляем только при выполнении всех условий."""
    if deal.net_profit is None or deal.roi_percent is None:
        return False
    return (
        deal.listing.is_active
        and deal.net_profit >= min_profit_ton
        and deal.roi_percent >= min_roi
    )
