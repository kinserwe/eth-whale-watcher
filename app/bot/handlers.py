import asyncio
import logging
from enum import StrEnum

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import case, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import InstrumentedAttribute

from app.database import SessionFactory
from app.models import AddressCategory, ScanState, Subscriber
from app.tokens import USDT

router = Router()

logger = logging.getLogger(__name__)


class SubscribeResult(StrEnum):
    CREATED = "created"
    REACTIVATED = "reactivated"
    ALREADY_ACTIVE = "already_active"
    NOT_READY = "not_ready"


class CategoryTogglePrefix(StrEnum):
    FROM = "from_toggle:"
    TO = "to_toggle:"


_START_REPLIES = {
    SubscribeResult.CREATED: "Subscribed successfully!",
    SubscribeResult.REACTIVATED: "Subscription reactivated successfully!",
    SubscribeResult.ALREADY_ACTIVE: "Subscription is already active!",
    SubscribeResult.NOT_READY: "Scan state for token not found.",
}

_CATEGORY_MAPPING = {
    AddressCategory.DEFI: "DeFi",
    AddressCategory.EXCHANGE: "Exchange",
    AddressCategory.MARKET_MAKER: "Market Maker",
    AddressCategory.TREASURY: "Treasury",
    AddressCategory.BRIDGE: "Bridge",
}


def _subscribe(chat_id: int) -> SubscribeResult:
    try:
        with SessionFactory.begin() as session:
            scan_state = session.get(ScanState, USDT.address)
            if scan_state is None:
                return SubscribeResult.NOT_READY

            sub = session.get(Subscriber, chat_id)
            if sub is None:
                session.add(
                    Subscriber(
                        chat_id=chat_id,
                        last_notified_block=scan_state.last_scanned_block,
                        is_active=True,
                    )
                )
                return SubscribeResult.CREATED
            if sub.is_active:
                return SubscribeResult.ALREADY_ACTIVE

            sub.is_active = True
            sub.last_notified_block = scan_state.last_scanned_block
            return SubscribeResult.REACTIVATED
    except IntegrityError:
        return SubscribeResult.ALREADY_ACTIVE


def _unsubscribe(chat_id: int):
    with SessionFactory.begin() as session:
        sub = session.get(Subscriber, chat_id)
        if sub is None:
            return

        sub.is_active = False


def _get_exclude_list(chat_id: int, column: InstrumentedAttribute) -> list[AddressCategory]:
    with SessionFactory.begin() as session:
        return session.execute(select(column).where(Subscriber.chat_id == chat_id)).scalar_one()


def _toggle_category(
    chat_id: int, category: AddressCategory, column: InstrumentedAttribute
) -> list[AddressCategory]:
    with SessionFactory.begin() as session:
        excluded_list = session.execute(
            update(Subscriber)
            .where(Subscriber.chat_id == chat_id)
            .values(
                {
                    column: case(
                        (column.contains([category]), func.array_remove(column, category)),
                        else_=func.array_append(column, category),
                    )
                }
            )
            .returning(column)
        ).scalar_one()
        return excluded_list


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


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    result = await asyncio.to_thread(_subscribe, message.chat.id)
    await message.answer(_START_REPLIES[result])


@router.message(Command("stop"))
async def handle_stop(message: Message) -> None:
    await asyncio.to_thread(_unsubscribe, message.chat.id)
    await message.answer("Subscription stopped!")


@router.message(Command("from"))
async def handle_from(message: Message) -> None:
    exclude_list = await asyncio.to_thread(
        _get_exclude_list, message.chat.id, Subscriber.from_categories_excluded
    )
    markup = _build_exclude_list_markup(exclude_list, CategoryTogglePrefix.FROM)
    await message.answer("choose visible categories for from_address", reply_markup=markup)


@router.message(Command("to"))
async def handle_to(message: Message) -> None:
    exclude_list = await asyncio.to_thread(
        _get_exclude_list, message.chat.id, Subscriber.to_categories_excluded
    )
    markup = _build_exclude_list_markup(exclude_list, CategoryTogglePrefix.TO)
    await message.answer("choose visible categories for to_address", reply_markup=markup)


@router.callback_query(F.data.startswith(CategoryTogglePrefix.FROM.value))
async def handle_from_category_toggle(callback: CallbackQuery) -> None:
    category = AddressCategory(callback.data.split(":")[1])
    logger.info("toggle from category %s", category)
    exclude_list = await asyncio.to_thread(
        _toggle_category, callback.message.chat.id, category, Subscriber.from_categories_excluded
    )
    markup = await asyncio.to_thread(
        _build_exclude_list_markup, exclude_list, CategoryTogglePrefix.FROM
    )
    await callback.message.edit_reply_markup(reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data.startswith(CategoryTogglePrefix.TO.value))
async def handle_to_category_toggle(callback: CallbackQuery) -> None:
    category = AddressCategory(callback.data.split(":")[1])
    logger.info("toggle to category %s", category)
    exclude_list = await asyncio.to_thread(
        _toggle_category, callback.message.chat.id, category, Subscriber.to_categories_excluded
    )
    markup = await asyncio.to_thread(
        _build_exclude_list_markup, exclude_list, CategoryTogglePrefix.FROM
    )
    await callback.message.edit_reply_markup(reply_markup=markup)
    await callback.answer()
