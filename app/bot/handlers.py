import asyncio
import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from app.bot.directions import DIRECTIONS
from app.bot.keyboards import build_exclude_list_markup, build_settings_markup
from app.bot.subscriptions import (
    SubscribeResult,
    get_exclude_list,
    subscribe,
    toggle_category,
    unsubscribe,
)
from app.models import AddressCategory

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
    result = await asyncio.to_thread(subscribe, message.chat.id)
    await message.answer(_START_REPLIES[result])


@router.message(Command("stop"))
async def handle_stop(message: Message) -> None:
    await asyncio.to_thread(unsubscribe, message.chat.id)
    await message.answer("Subscription stopped!")


@router.message(Command("settings"))
async def handle_settings(message: Message) -> None:
    markup = build_settings_markup()
    await message.answer("Settings:", reply_markup=markup)


@router.callback_query(F.data == "settings:return")
async def handle_settings_return(callback: CallbackQuery) -> None:
    await callback.message.edit_text("Settings:", reply_markup=build_settings_markup())
    await callback.answer()


@router.callback_query(F.data.in_({f"settings:{slug}" for slug in DIRECTIONS}))
async def handle_direction_menu(callback: CallbackQuery) -> None:
    _, option = callback.data.split(":")

    direction = DIRECTIONS[option]
    exclude_list = await asyncio.to_thread(
        get_exclude_list, callback.message.chat.id, direction.column
    )
    markup = build_exclude_list_markup(exclude_list, direction)
    await callback.message.edit_text(
        f"choose visible categories for {direction.noun}", reply_markup=markup
    )
    await callback.answer()


@router.callback_query(F.data.startswith("toggle:"))
async def handle_category_toggle(callback: CallbackQuery) -> None:
    _, slug, category = callback.data.split(":")
    direction = DIRECTIONS[slug]
    exclude_list = await asyncio.to_thread(
        toggle_category, callback.message.chat.id, AddressCategory(category), direction.column
    )
    markup = await asyncio.to_thread(build_exclude_list_markup, exclude_list, direction)
    await callback.message.edit_reply_markup(reply_markup=markup)
    await callback.answer()
