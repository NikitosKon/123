from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.adapters.getgems import GetgemsAdapter
from app.adapters.portals import PortalsAdapter
from app.adapters.tonnel import TonnelAdapter
from app.bot.formatters import format_deal
from app.domain.enums import Currency, Marketplace
from app.domain.models import FloorQuote, NormalizedListing, RecentSale
from app.services.profit import analyze_deal
from app.services.valuation import estimate_resale, select_resale_listing


def _listing(
    listing_id: str,
    price: str,
    backdrop: str,
    *,
    marketplace: Marketplace = Marketplace.GETGEMS,
) -> NormalizedListing:
    return NormalizedListing(
        marketplace=marketplace,
        listing_id=listing_id,
        gift_name="Precious Peach",
        model="Angelic",
        backdrop=backdrop,
        price=Decimal(price),
        currency=Currency.TON,
    )


def _sale(price: str, backdrop: str) -> RecentSale:
    return RecentSale(
        marketplace=Marketplace.GETGEMS,
        listing_id=f"sale-{price}-{backdrop}",
        gift_name="Precious Peach",
        model="Angelic",
        backdrop=backdrop,
        price=Decimal(price),
        currency=Currency.TON,
        sold_at=datetime.now(timezone.utc) - timedelta(days=1),
    )


def test_black_and_onyx_black_are_canonicalized_with_rarity():
    black = _listing("black", "100", "black (0.08%)")
    onyx = NormalizedListing(
        marketplace=Marketplace.GETGEMS,
        listing_id="onyx",
        gift_name="Precious Peach",
        model="Angelic",
        backdrop={"value": "onyx black", "rarity": "0.02%"},
        price=Decimal("100"),
    )

    assert black.backdrop == "Black"
    assert black.backdrop_rarity_pct == Decimal("0.08")
    assert onyx.backdrop == "Onyx Black"
    assert onyx.backdrop_rarity_pct == Decimal("0.02")


def test_portals_parser_keeps_rare_backgrounds():
    adapter = PortalsAdapter(auth_data="test-init-data", enabled=True)
    black = adapter.normalize_listing(
        {
            "id": "portal-black",
            "name": "Precious Peach #1",
            "price": "100",
            "attributes": [{"type": "Backdrop", "value": "Black"}],
        }
    )
    onyx = adapter.normalize_listing(
        {
            "id": "portal-onyx",
            "name": "Precious Peach #2",
            "price": "100",
            "attributes": [{"type": "Backdrop", "value": "ONYX BLACK"}],
        }
    )

    assert black is not None and black.backdrop == "Black"
    assert onyx is not None and onyx.backdrop == "Onyx Black"


def test_getgems_parser_keeps_rare_background_and_rarity():
    adapter = GetgemsAdapter(api_key="test", enabled=True)
    listing = adapter.normalize_listing(
        {
            "address": "nft-black",
            "name": "Precious Peach #3",
            "sale": {"fullPrice": "100000000000", "currency": "TON"},
            "attributes": [
                {"traitType": "Model", "value": "Angelic"},
                {"traitType": "Backdrop", "value": {"name": "Black", "rarity": "0.03%"}},
            ],
        }
    )

    assert listing is not None
    assert listing.backdrop == "Black"
    assert listing.backdrop_rarity_pct == Decimal("0.03")


def test_tonnel_parser_keeps_rare_background_and_rarity():
    listing = TonnelAdapter(enabled=True).normalize_listing(
        {
            "gift_id": 99,
            "name": "Precious Peach",
            "model": "Angelic (3%)",
            "backdrop": "onyx black (0.04%)",
            "price": "100",
            "status": "forsale",
        }
    )

    assert listing is not None
    assert listing.backdrop == "Onyx Black"
    assert listing.backdrop_rarity_pct == Decimal("0.04")


def test_resale_ignores_other_backdrops_for_matching_listing():
    target = _listing("buy", "100", "Black")
    wrong_background = _listing("onyx", "80", "Onyx Black", marketplace=Marketplace.PORTALS)
    matching_background = _listing("black-comp", "120", "Black", marketplace=Marketplace.PORTALS)

    assert select_resale_listing(target, [target, wrong_background, matching_background]) is matching_background


def test_single_high_rare_backdrop_ask_does_not_inflate_profit_estimate():
    target = _listing("buy", "100", "Black")
    joke_ask = _listing("joke", "600", "Black", marketplace=Marketplace.PORTALS)
    regular_background = _listing("blue", "150", "Blue", marketplace=Marketplace.TONNEL)

    estimate = estimate_resale(
        target,
        [target, joke_ask, regular_background],
        [_sale("150", "Blue")],
    )

    assert estimate.price == Decimal("150")
    assert estimate.backdrop_floor == Decimal("600")
    assert estimate.backdrop_comparable_count == 1
    assert estimate.backdrop_sales_count == 0
    assert "нет продаж этого фона" in estimate.basis


def test_confirmed_rare_background_sale_can_support_a_premium():
    target = _listing("buy", "100", "Black")
    joke_ask = _listing("joke", "600", "Black", marketplace=Marketplace.PORTALS)
    regular_background = _listing("blue", "150", "Blue", marketplace=Marketplace.TONNEL)

    estimate = estimate_resale(
        target,
        [target, joke_ask, regular_background],
        [_sale("150", "Blue"), _sale("220", "Black")],
    )

    assert estimate.price == Decimal("220")
    assert estimate.recent_sales_median == Decimal("220")
    assert estimate.backdrop_sales_median == Decimal("220")
    assert estimate.backdrop_sales_count == 1
    assert estimate.basis == "листинги и продажи того же фона"


def test_deal_message_shows_rare_backdrop_evidence():
    target = _listing("buy", "100", "Black")
    deal = analyze_deal(
        target,
        buy_fee_pct=Decimal("0"),
        sell_price=Decimal("220"),
        backdrop_floor=FloorQuote(
            kind="backdrop_floor", value=Decimal("600"), listings_count=1
        ),
        backdrop_sales_median=Decimal("220"),
        backdrop_sales_count=1,
        backdrop_comparable_count=1,
    )

    assert (
        "🖤 Black: floor 600 TON · 1 лист. / 1 продаж · медиана 220 TON"
        in format_deal(deal)
    )
