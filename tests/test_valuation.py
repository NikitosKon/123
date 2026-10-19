import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.adapters.getgems import GetgemsAdapter
from app.domain.enums import Currency, Marketplace
from app.domain.models import NormalizedListing, RecentSale
from app.services.profit import analyze_deal, is_worth_alert
from app.services.valuation import estimate_resale, select_resale_listing


def listing(
    marketplace: Marketplace,
    listing_id: str,
    price: str,
    *,
    model: str = "Angelic",
    gift_name: str = "Precious Peach",
) -> NormalizedListing:
    return NormalizedListing(
        marketplace=marketplace,
        listing_id=listing_id,
        gift_name=gift_name,
        model=model,
        price=Decimal(price),
        currency=Currency.TON,
    )


def sale(price: str, *, days_ago: int = 1, model: str = "Angelic") -> RecentSale:
    return RecentSale(
        marketplace=Marketplace.GETGEMS,
        listing_id=f"sale-{price}-{days_ago}-{model}",
        gift_name="Precious Peach",
        model=model,
        price=Decimal(price),
        currency=Currency.TON,
        sold_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
    )


def test_cross_market_comparable_listing_is_used():
    target = listing(Marketplace.GETGEMS, "buy", "100")
    other_market = listing(Marketplace.PORTALS, "peer", "125")

    assert select_resale_listing(target, [target, other_market]) is other_market


def test_sales_median_caps_inflated_active_ask():
    # The listing under consideration is 200 TON. A joke ask is 600 TON,
    # while actual recent sales center around 150 TON.
    target = listing(Marketplace.GETGEMS, "buy", "200")
    inflated_ask = listing(Marketplace.PORTALS, "joke", "600")
    estimate = estimate_resale(
        target,
        [target, inflated_ask],
        [sale("149"), sale("150"), sale("151")],
        marketplaces_compared=[Marketplace.GETGEMS, Marketplace.PORTALS, Marketplace.TONNEL],
    )

    assert estimate.price == Decimal("150")
    assert estimate.recent_sales_median == Decimal("150")
    assert estimate.recent_sales_count == 3
    assert estimate.active_comparable_count == 1
    assert estimate.marketplaces_compared == [
        Marketplace.GETGEMS,
        Marketplace.PORTALS,
        Marketplace.TONNEL,
    ]
    deal = analyze_deal(
        target,
        buy_fee_pct=Decimal("0.02"),
        sell_price=estimate.price,
        sell_fee_pct=Decimal("0.05"),
    )
    assert not is_worth_alert(deal, min_profit_ton=Decimal("0.2"), min_roi=Decimal("10"))


def test_old_sales_and_other_models_do_not_change_estimate():
    target = listing(Marketplace.GETGEMS, "buy", "100")
    fresh_sales = [sale("105"), sale("107", model="Other Model")]
    old_sale = sale("1", days_ago=45)
    estimate = estimate_resale(
        target,
        [],
        [*fresh_sales, old_sale],
        as_of=datetime.now(timezone.utc),
    )

    assert estimate.price == Decimal("105")
    assert estimate.recent_sales_count == 1
    assert estimate.basis == "медиана фактических продаж"


def test_without_sales_uses_cheapest_cross_market_active_listing():
    target = listing(Marketplace.GETGEMS, "buy", "100")
    cheaper = listing(Marketplace.TONNEL, "cheap", "95")
    expensive = listing(Marketplace.PORTALS, "expensive", "140")

    estimate = estimate_resale(target, [target, expensive, cheaper], [])

    assert estimate.price == Decimal("95")
    assert estimate.marketplace == Marketplace.TONNEL
    assert estimate.recent_sales_count == 0
    assert estimate.basis == "минимум активных сопоставимых листингов"


def test_getgems_history_is_normalized_and_cached_by_gift(monkeypatch):
    adapter = GetgemsAdapter(api_key="test", enabled=True)
    adapter._collections_by_gift["precious peach"] = {("collection", False)}
    now = datetime.now(timezone.utc)
    events = [
        {
            "address": "nft-1",
            "time": now.isoformat(),
            "typeData": {"type": "sold", "priceNano": "150000000000", "currency": "TON"},
        },
        {
            "address": "nft-2",
            "time": now.isoformat(),
            "typeData": {"type": "sold", "price": "170", "currency": "TON"},
        },
    ]
    details = {
        "nft-1": {
            "address": "nft-1",
            "name": "Precious Peach #1711",
            "attributes": [{"traitType": "Model", "value": "Angelic"}],
        },
        "nft-2": {
            "address": "nft-2",
            "name": "Precious Peach #1712",
            "attributes": [{"traitType": "Model", "value": "Other Model"}],
        },
    }
    calls = []

    async def fake_request(method, path, *, params=None, json_body=None):
        calls.append((method, path))
        if method == "GET":
            assert params["types"] == "sold"
            return {"items": events}
        return {"items": [details[address] for address in json_body["addressList"]]}

    monkeypatch.setattr(adapter, "_request", fake_request)

    async def fetch():
        since = now - timedelta(days=30)
        angelic = await adapter.fetch_recent_sales("Precious Peach", "Angelic", since)
        other = await adapter.fetch_recent_sales("Precious Peach", "Other Model", since)
        return angelic, other

    angelic, other = asyncio.run(fetch())

    assert [(item.model, item.price) for item in angelic] == [("Angelic", Decimal("150"))]
    assert [(item.model, item.price) for item in other] == [("Other Model", Decimal("170"))]
    assert sum(1 for method, _ in calls if method == "GET") == 1
