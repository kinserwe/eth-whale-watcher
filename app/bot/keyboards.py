from aiogram.enums import ButtonStyle
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

TOKEN_THRESHOLDS = [1_000_000, 5_000_000, 20_000_000, 50_000_000]


def build_exclude_list_markup(
    exclude_list: list[AddressCategory], direction: Direction
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(
        *[
            InlineKeyboardButton(
                text=_CATEGORY_MAPPING[category],
                style=ButtonStyle.DANGER if category in exclude_list else ButtonStyle.SUCCESS,
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
    builder.add(
        InlineKeyboardButton(text="from", callback_data=f"settings:{FROM.slug}"),
        InlineKeyboardButton(text="to", callback_data=f"settings:{TO.slug}"),
        InlineKeyboardButton(text="threshold", callback_data="settings:threshold"),
    )
    builder.adjust(2)
    return builder.as_markup()


def build_threshold_select_markup(current_threshold: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        *[
            InlineKeyboardButton(
                text=f"{t / 10**6:.0f}M",
                callback_data=f"settings:threshold:{t}",
                **({"style": ButtonStyle.SUCCESS} if t == current_threshold else {}),
            )
            for t in TOKEN_THRESHOLDS
        ]
    )
    builder.row(InlineKeyboardButton(text="Return", callback_data="settings:return"))
    return builder.as_markup()
