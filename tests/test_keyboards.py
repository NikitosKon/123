from decimal import Decimal

from app.adapters.portals import PortalsAdapter
from app.bot.keyboards import deal_keyboard
from app.domain.enums import Marketplace
from app.services.profit import analyze_deal


def test_portals_deal_keyboard_has_both_gift_and_purchase_links():
    listing = PortalsAdapter(auth_data="init-data", enabled=True).normalize_listing(
        {
            "id": "portal-listing-1",
            "name": "Big Year #827",
            "price": "12.5",
            "status": "listed",
        }
    )
    assert listing is not None
    deal = analyze_deal(
        listing,
        buy_fee_pct=Decimal("0.065"),
        sell_price=Decimal("15"),
        sell_marketplace=Marketplace.GETGEMS,
        sell_fee_pct=Decimal("0.05"),
    )

    buttons = [button for row in deal_keyboard(deal).inline_keyboard for button in row]
    urls = {button.url for button in buttons if button.url}
    assert "https://t.me/nft/BigYear-827" in urls
    assert "https://t.me/portals/market?startapp=gift_portal-listing-1" in urls
