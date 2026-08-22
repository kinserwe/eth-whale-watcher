from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.directions import FROM, TO, Direction
from app.models import AddressCategory

_CATEGORY_MAPPING = {
    AddressCategory.DEFI: "DeFi",
    AddressCategory.EXCHANGE: "Exchange",
    AddressCategory.MARKET_MAKER: "Market Maker",
    AddressCategory.TREASURY: "Treasury",
    AddressCategory.BRIDGE: "Bridge",
}


def _build_exclude_list_markup(
    exclude_list: list[AddressCategory], direction: Direction
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(
        *[
            InlineKeyboardButton(
                text=_CATEGORY_MAPPING[category],
                style="danger" if category in exclude_list else "success",
                callback_data=f"toggle:{direction.slug}:{category}",
            )
            for category in AddressCategory
        ],
    )
    builder.adjust(3)
    builder.row(InlineKeyboardButton(text="Return", callback_data="settings:return"))
    return builder.as_markup()


def build_settings_markup() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="from", callback_data=f"settings:{FROM.slug}"),
        InlineKeyboardButton(text="to", callback_data=f"settings:{TO.slug}"),
    )
    return builder.as_markup()
