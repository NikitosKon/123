from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.domain.enums import Currency, Marketplace
from app.domain.models import RecentSale
from app.services.recommendations import classify_sale
from app.storage.models import Recommendation


def test_confirmed_later_sale_is_classified_as_flip_when_price_is_higher():
    recommended_at = datetime.now(timezone.utc) - timedelta(hours=2)
    recommendation = Recommendation(
        gift_name="Precious Peach",
        gift_num=1711,
        model="Angelic",
        buy_price=Decimal("100"),
        created_at=recommended_at,
    )
    sale = RecentSale(
        marketplace=Marketplace.GETGEMS,
        gift_name="Precious Peach",
        gift_num=1711,
        model="Angelic",
        price=Decimal("150"),
        currency=Currency.TON,
        sold_at=recommended_at + timedelta(hours=1),
    )

    assert classify_sale(sale, recommendation) == "flipped"


def test_sale_below_recommended_price_is_not_called_a_flip():
    recommended_at = datetime.now(timezone.utc) - timedelta(hours=2)
    recommendation = Recommendation(
        gift_name="Precious Peach",
        gift_num=1711,
        model="Angelic",
        buy_price=Decimal("150"),
        created_at=recommended_at,
    )
    sale = RecentSale(
        marketplace=Marketplace.GETGEMS,
        gift_name="Precious Peach",
        gift_num=1711,
        model="Angelic",
        price=Decimal("125"),
        currency=Currency.TON,
        sold_at=recommended_at + timedelta(hours=1),
    )

    assert classify_sale(sale, recommendation) == "sold"


def test_sale_must_match_exact_gift_number_and_be_after_recommendation():
    recommended_at = datetime.now(timezone.utc)
    recommendation = Recommendation(
        gift_name="Precious Peach",
        gift_num=1711,
        model="Angelic",
        buy_price=Decimal("100"),
        created_at=recommended_at,
    )
    wrong_number = RecentSale(
        marketplace=Marketplace.GETGEMS,
        gift_name="Precious Peach",
        gift_num=1712,
        model="Angelic",
        price=Decimal("200"),
        currency=Currency.TON,
        sold_at=recommended_at + timedelta(minutes=1),
    )
    earlier = RecentSale(
        marketplace=Marketplace.GETGEMS,
        gift_name="Precious Peach",
        gift_num=1711,
        model="Angelic",
        price=Decimal("200"),
        currency=Currency.TON,
        sold_at=recommended_at - timedelta(minutes=1),
    )

    assert classify_sale(wrong_number, recommendation) is None
    assert classify_sale(earlier, recommendation) is None
