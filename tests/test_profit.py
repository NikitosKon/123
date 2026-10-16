import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.adapters.tonnel import TonnelAdapter
from app.services.profit import analyze_deal, is_worth_alert

FIX = Path(__file__).parent / "fixtures" / "tonnel_gifts.json"


@pytest.fixture()
def listing():
    a = TonnelAdapter(enabled=True)
    return a.normalize_listing(json.loads(FIX.read_text())[0])


def test_profit_formula(listing):
    # buy 4.8 TON, fee 10% -> 0.48; sell 6.12, sell fee 5% -> 0.306
    deal = analyze_deal(
        listing,
        buy_fee_pct=Decimal("0.10"),
        sell_price=Decimal("6.12"),
        sell_fee_pct=Decimal("0.05"),
        transfer_fee_ton=Decimal("0.03"),
        network_fee_ton=Decimal("0.05"),
        slippage_reserve_ton=Decimal("0.05"),
    )
    # entry = 4.8 + 0.48 + 0.03 + 0.05 + 0.05 = 5.41
    assert deal.total_costs == Decimal("0.61")
    # exit = 6.12 - 0.306 - 0.05 = 5.764
    # net = 5.764 - 5.41 = 0.354 -> 0.35
    assert deal.net_profit == Decimal("0.35")
    # roi = 0.354/5.41*100 = 6.54...
    assert deal.roi_percent == Decimal("6.54")
    assert deal.status == "estimated"  # нет исполнимых bids


def test_confirmed_with_bids(listing):
    deal = analyze_deal(
        listing,
        buy_fee_pct=Decimal("0.10"),
        sell_price=Decimal("6.12"),
        sell_fee_pct=Decimal("0.05"),
        has_executable_bids=True,
    )
    assert deal.status == "confirmed"


def test_no_exit_price_no_profit(listing):
    deal = analyze_deal(listing, buy_fee_pct=Decimal("0.10"), sell_price=None)
    assert deal.net_profit is None
    assert deal.roi_percent is None
    assert deal.status == "estimated"


def test_worth_alert_thresholds(listing):
    deal = analyze_deal(
        listing,
        buy_fee_pct=Decimal("0.10"),
        sell_price=Decimal("6.12"),
        sell_fee_pct=Decimal("0.05"),
    )
    assert is_worth_alert(deal, min_profit_ton=Decimal("0.2"), min_roi=Decimal("5"))
    assert not is_worth_alert(deal, min_profit_ton=Decimal("1"), min_roi=Decimal("5"))
    assert not is_worth_alert(deal, min_profit_ton=Decimal("0.2"), min_roi=Decimal("50"))


def test_inactive_listing_no_alert(listing):
    listing.is_active = False
    deal = analyze_deal(
        listing, buy_fee_pct=Decimal("0.10"), sell_price=Decimal("10"), sell_fee_pct=Decimal("0")
    )
    assert not is_worth_alert(deal, min_profit_ton=Decimal("0"), min_roi=Decimal("0"))
