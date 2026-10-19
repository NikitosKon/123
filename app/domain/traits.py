"""Normalization helpers for Telegram gift traits."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

_BACKDROP_LABELS = {
    "black": "Black",
    "onyx black": "Onyx Black",
}
_RARITY_SUFFIX = re.compile(r"^(?P<name>.*?)\s*\(\s*(?P<rarity>\d+(?:\.\d+)?)\s*%\s*\)\s*$")


def trait_text(value: Any) -> str:
    """Extract a readable trait label from string or structured API values."""
    if isinstance(value, dict):
        value = value.get("value") or value.get("name") or value.get("label") or ""
    return str(value or "").strip()


def normalize_backdrop(value: Any, rarity: Any = None) -> tuple[str, Decimal | None]:
    """Return a stable backdrop label and optional rarity percentage.

    A few APIs inline rarity into the value (``Black (0.2%)``), while others
    provide a separate rarity field. Preserve all backdrop names, but use
    canonical capitalization for the rare Black variants.
    """
    if isinstance(value, dict):
        data = value
        rarity = rarity if rarity is not None else (
            data.get("rarity") or data.get("rarity_pct") or data.get("rarityPercent")
        )
        value = data.get("value") or data.get("name") or data.get("label") or ""

    name = trait_text(value)
    match = _RARITY_SUFFIX.fullmatch(name)
    if match:
        name = match.group("name").strip()
        if rarity is None:
            rarity = match.group("rarity")

    backdrop_key = name.casefold()
    name = _BACKDROP_LABELS.get(backdrop_key, name)
    if rarity is None:
        return name, None

    rarity_text = str(rarity).strip().removesuffix("%").strip()
    try:
        parsed_rarity = Decimal(rarity_text)
    except (InvalidOperation, ValueError):
        parsed_rarity = None
    return name, parsed_rarity
