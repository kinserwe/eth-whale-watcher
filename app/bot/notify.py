import asyncio
import logging
from dataclasses import dataclass

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from sqlalchemy import func, select, update

from app.database import SessionFactory
from app.models import ScanState, Subscriber, Transfer
from app.tokens import Token

_NOTIFY_INTERVAL_SECONDS = 30
_MAX_CATCHUP_BLOCKS = 3600
_ETHERSCAN_URL_PREFIX = "https://etherscan.io/tx/"

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Notification:
    chat_id: int
    text: str


@dataclass(frozen=True)
class NotifyBatch:
    cursor: int
    notifications: list[Notification]


def _fetch(token: Token) -> NotifyBatch:
    with SessionFactory.begin() as session:
        subs = session.execute(select(Subscriber).where(Subscriber.is_active)).scalars().all()

        if not subs:
            return NotifyBatch(0, [])

        state = session.get(ScanState, token.address)
        if not state:
            return NotifyBatch(0, [])

        head = state.last_scanned_block
        floor = min(sub.last_notified_block for sub in subs)
        transfers = (
            session.execute(
                select(Transfer)
                .where(
                    Transfer.block_number > floor,
                    Transfer.block_number <= head,
                    Transfer.token_address == token.address,
                )
                .order_by(Transfer.block_number)
                .limit(50)
            )
            .scalars()
            .all()
        )
        if not transfers:
            return NotifyBatch(0, [])

        notifications = []
        for sub in subs:
            filtered_transfers = [t for t in transfers if t.block_number > sub.last_notified_block]
            if len(filtered_transfers) == 0:
                continue
            text = "\n".join(
                f"from: {t.from_address}"
                f" | to: {t.to_address}"
                f" | value: {token.from_raw(t.value):,.0f}"
                f" | etherscan: {_ETHERSCAN_URL_PREFIX}{t.tx_hash}"
                for t in filtered_transfers
            )
            notifications.append(Notification(sub.chat_id, text))
        return NotifyBatch(transfers[-1].block_number, notifications)


def _advance(chat_ids: list[int], new_cursor: int) -> None:
    with SessionFactory.begin() as session:
        session.execute(
            update(Subscriber)
            .where(Subscriber.chat_id.in_(chat_ids))
            .values(last_notified_block=func.greatest(Subscriber.last_notified_block, new_cursor))
        )


def _deactivate(chat_id: int) -> None:
    with SessionFactory.begin() as session:
        sub = session.get(Subscriber, chat_id)
        if sub:
            sub.is_active = False


def _skip_stale(token: Token) -> NotifyBatch:
    with SessionFactory.begin() as session:
        state = session.get(ScanState, token.address)
        if not state:
            return NotifyBatch(0, [])

        head = state.last_scanned_block
        subs = (
            session.execute(
                select(Subscriber).where(
                    Subscriber.is_active,
                    head - Subscriber.last_notified_block > _MAX_CATCHUP_BLOCKS,
                )
            )
            .scalars()
            .all()
        )
        if not subs:
            return NotifyBatch(0, [])

        notifications = []
        for sub in subs:
            missed = session.scalar(
                select(func.count())
                .select_from(Transfer)
                .where(
                    Transfer.block_number > sub.last_notified_block,
                    Transfer.block_number <= head,
                    Transfer.token_address == token.address,
                )
            )
            notifications.append(
                Notification(
                    sub.chat_id,
                    f"Skipped {missed} {token.symbol} transfers while the bot was offline.",
                )
            )

        return NotifyBatch(head, notifications)


async def _send_batch(bot: Bot, batch: NotifyBatch) -> None:
    sent: list[int] = []
    for n in batch.notifications:
        try:
            await bot.send_message(n.chat_id, n.text)
            sent.append(n.chat_id)
        except TelegramForbiddenError:
            await asyncio.to_thread(_deactivate, n.chat_id)
        except TelegramBadRequest as exc:
            if "chat not found" in exc.message:
                await asyncio.to_thread(_deactivate, n.chat_id)
            else:
                logger.exception("send failed for %s", n.chat_id)
        except Exception:
            logger.exception("send failed for %s", n.chat_id)
    if sent:
        await asyncio.to_thread(_advance, sent, batch.cursor)


async def _notify_once(bot: Bot, token: Token) -> None:
    await _send_batch(bot, await asyncio.to_thread(_skip_stale, token))
    await _send_batch(bot, await asyncio.to_thread(_fetch, token))


async def notify_loop(bot: Bot, token: Token) -> None:
    while True:
        try:
            await _notify_once(bot, token)
        except Exception:
            logger.exception("notify_cycle_failed")
        await asyncio.sleep(_NOTIFY_INTERVAL_SECONDS)
