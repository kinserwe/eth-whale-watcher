import asyncio
from enum import StrEnum

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from sqlalchemy.exc import IntegrityError

from app.database import SessionFactory
from app.models import ScanState, Subscriber
from app.tokens import USDT

router = Router()


class SubscribeResult(StrEnum):
    CREATED = "created"
    REACTIVATED = "reactivated"
    ALREADY_ACTIVE = "already_active"
    NOT_READY = "not_ready"


_START_REPLIES = {
    SubscribeResult.CREATED: "Subscribed successfully!",
    SubscribeResult.REACTIVATED: "Subscription reactivated successfully!",
    SubscribeResult.ALREADY_ACTIVE: "Subscription is already active!",
    SubscribeResult.NOT_READY: "Scan state for token not found.",
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
            return SubscribeResult.REACTIVATED
    except IntegrityError:
        return SubscribeResult.ALREADY_ACTIVE


def _unsubscribe(chat_id: int):
    with SessionFactory.begin() as session:
        sub = session.get(Subscriber, chat_id)
        if sub is None:
            return

        sub.is_active = False


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    result = await asyncio.to_thread(_subscribe, message.chat.id)
    await message.answer(_START_REPLIES[result])


@router.message(Command("stop"))
async def handle_stop(message: Message) -> None:
    await asyncio.to_thread(_unsubscribe, message.chat.id)
    await message.answer("Subscription stopped!")
