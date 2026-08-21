from enum import StrEnum

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.models import AddressCategory


class CategoryTogglePrefix(StrEnum):
    FROM = "from_toggle:"
    TO = "to_toggle:"


_CATEGORY_MAPPING = {
    AddressCategory.DEFI: "DeFi",
    AddressCategory.EXCHANGE: "Exchange",
    AddressCategory.MARKET_MAKER: "Market Maker",
    AddressCategory.TREASURY: "Treasury",
    AddressCategory.BRIDGE: "Bridge",
}


def _build_exclude_list_markup(
    exclude_list: list[AddressCategory], prefix: CategoryTogglePrefix
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(
        *[
            InlineKeyboardButton(
                text=_CATEGORY_MAPPING[category],
                style="danger" if category in exclude_list else "success",
                callback_data=f"{prefix.value}{category}",
            )
            for category in AddressCategory
        ]
    )
    builder.adjust(3)
    return builder.as_markup()
