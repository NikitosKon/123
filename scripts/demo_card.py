"""Генерация демо-карточки уведомления без запуска бота.

Использование: python scripts/demo_card.py [out.png]
Изображение: assets/demo/surgeboard-183.webp — РЕАЛЬНЫЙ NFT-подарок Surge Board
с моделью Hoverboard (Fragment CDN). Конкретный #29348 на момент сборки не
заминчен как NFT (nft.fragment.com/gift/surgeboard-29348.json -> 404), поэтому
для превью взят оригинал той же модели. В бою изображение резолвится из данных
листинга (Fragment CDN / custom_emoji_id / TON metadata).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.bot.cards import CardData, render_card


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "card_preview.png")
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
        image_path=Path("assets/demo/surgeboard-183.webp"),
    )
    path = render_card(data, out)
    print(f"saved: {path}")


if __name__ == "__main__":
    main()
