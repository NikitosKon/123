from pathlib import Path

from app.bot.cards import CardData, render_card


def test_render_card(tmp_path):
    demo_img = Path("assets/demo/surgeboard-183.webp")
    data = CardData(
        gift_name="Surge Board",
        gift_num=29348,
        emoji="🏄",
        owner_username="stos7",
        owner_id=540569068,
        model="Hoverboard",
        model_rarity="3%",
        backdrop="Midnight Blue",
        backdrop_rarity="1.5%",
        symbol="Lion Head",
        symbol_rarity="0.4%",
        floor_value="6.12",
        floor_currency="GRAM",
        floor_updated="3 мин. назад",
        transferable=True,
        availability_issued=29348,
        availability_total=39464,
        buy_price="4.80 GRAM",
        gift_floor="5.90 GRAM",
        model_floor="6.12 GRAM",
        exact_floor="7.40 GRAM",
        profit="+1.85 GRAM",
        roi="+38.5%",
        image_path=demo_img if demo_img.exists() else None,
    )
    out = render_card(data, tmp_path / "card.png", fonts_dir="assets/fonts")
    assert out.exists() and out.stat().st_size > 50_000


def test_render_card_without_image(tmp_path):
    data = CardData(
        gift_name="Plush Pepe",
        gift_num=1842,
        model="Diamond",
        model_rarity="1.5%",
        backdrop="Blue",
        backdrop_rarity="2%",
        symbol="Star",
        symbol_rarity="0.5%",
        floor_value="1.55",
        floor_currency="TON",
        floor_updated="12 сек. назад",
        transferable=False,
        availability_issued=1842,
        availability_total=10000,
    )
    out = render_card(data, tmp_path / "card2.png", fonts_dir="assets/fonts")
    assert out.exists() and out.stat().st_size > 30_000
