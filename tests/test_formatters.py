"""Проверка обязательной прямой ссылки в уведомлении о сделке."""
import json
from decimal import Decimal
from pathlib import Path

from app.adapters.tonnel import TonnelAdapter
from app.bot.formatters import format_deal, telegram_gift_url
from app.domain.enums import Marketplace
from app.domain.models import FloorQuote
from app.services.profit import analyze_deal


def test_deal_message_contains_direct_marketplace_link():
    fixture = Path(__file__).parent / "fixtures" / "tonnel_gifts.json"
    listing = TonnelAdapter(enabled=True).normalize_listing(json.loads(fixture.read_text())[0])
    assert listing is not None

    deal = analyze_deal(
        listing,
        buy_fee_pct=Decimal("0.10"),
        sell_price=Decimal("6.12"),
        sell_marketplace=Marketplace.TONNEL,
        sell_fee_pct=Decimal("0.05"),
        gift_floor=FloorQuote(
            kind="gift_floor", value=Decimal("4.8"), marketplace=Marketplace.TONNEL
        ),
        model_floor=FloorQuote(
            kind="model_floor", value=Decimal("6.12"), marketplace=Marketplace.TONNEL
        ),
    )
    message = format_deal(deal)

    assert 'href="https://t.me/nft/SurgeBoard-29348"' in message
    assert "Открыть подарок в Telegram" in message
    assert "💎 Цена: 4.8 TON (tonnel)" in message
    assert "🔒 Передача: ✅ доступна" in message
    assert "💸 Потенциальная цена выхода: 6.12 TON" in message
    assert "💰 Потенциальный профит по оценке: ≈ +" in message
    assert "фактическая цена и срок продажи не гарантированы" in message
    assert "Флор подарка: 4.8 TON (tonnel)" in message
    assert "Флор модели: 6.12 TON (tonnel)" in message
    assert message.splitlines()[-1].endswith("Открыть подарок в Telegram</a>")


def test_telegram_gift_link_uses_telegram_slug_when_available():
    listing = TonnelAdapter(enabled=True).normalize_listing(
        {"name": "Precious Peach", "gift_num": 1711, "gift_id": 1, "price": 1049, "status": "forsale"}
    )
    assert listing is not None
    assert telegram_gift_url(listing) == "https://t.me/nft/PreciousPeach-1711"
