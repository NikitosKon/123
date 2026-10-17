"""Проверка обязательной прямой ссылки в уведомлении о сделке."""
import json
from decimal import Decimal
from pathlib import Path

from app.adapters.tonnel import TonnelAdapter
from app.bot.formatters import format_deal
from app.services.profit import analyze_deal


def test_deal_message_contains_direct_marketplace_link():
    fixture = Path(__file__).parent / "fixtures" / "tonnel_gifts.json"
    listing = TonnelAdapter(enabled=True).normalize_listing(json.loads(fixture.read_text())[0])
    assert listing is not None

    deal = analyze_deal(
        listing,
        buy_fee_pct=Decimal("0.10"),
        sell_price=Decimal("6.12"),
        sell_fee_pct=Decimal("0.05"),
    )
    message = format_deal(deal)

    assert f'href="{listing.url}"' in message
    assert "Открыть подарок на маркетплейсе" in message
