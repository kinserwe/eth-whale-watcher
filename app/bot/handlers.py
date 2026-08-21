import asyncio
import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards import CategoryTogglePrefix, _build_exclude_list_markup
from app.bot.subscriptions import (
    SubscribeResult,
    _get_exclude_list,
    _subscribe,
    _toggle_category,
    _unsubscribe,
)
from app.models import AddressCategory, Subscriber

router = Router()

logger = logging.getLogger(__name__)

_START_REPLIES = {
    SubscribeResult.CREATED: "Subscribed successfully!",
    SubscribeResult.REACTIVATED: "Subscription reactivated successfully!",
    SubscribeResult.ALREADY_ACTIVE: "Subscription is already active!",
    SubscribeResult.NOT_READY: "Scan state for token not found.",
}


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
