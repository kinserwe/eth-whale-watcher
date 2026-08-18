import asyncio
import logging
from dataclasses import dataclass

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import aliased

from app.database import SessionFactory
from app.models import AddressCategory, AddressLabel, ScanState, Subscriber, Transfer
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


def _is_excluded(label: AddressLabel | None, exclude: list[AddressCategory]) -> bool:
    if label is None:
        return False

    return label.category in exclude


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
        from_alias = aliased(AddressLabel, name="from_label")
        to_alias = aliased(AddressLabel, name="to_label")
        rows = session.execute(
            select(Transfer, from_alias, to_alias)
            .outerjoin(from_alias, Transfer.from_address == from_alias.address)
            .outerjoin(to_alias, Transfer.to_address == to_alias.address)
            .where(
                Transfer.block_number > floor,
                Transfer.block_number <= head,
                Transfer.token_address == token.address,
                or_(
                    from_alias.entity.is_(None),
                    to_alias.entity.is_(None),
                    from_alias.entity != to_alias.entity,
                ),
            )
            .order_by(Transfer.block_number)
            .limit(50)
        ).all()
        if not rows:
            return NotifyBatch(0, [])
        notifications = []
        for sub in subs:
            filtered_rows = [
                r
                for r in rows
                if r.Transfer.block_number > sub.last_notified_block
                and (
                    not _is_excluded(r.from_label, sub.from_categories_excluded)
                    and not _is_excluded(r.to_label, sub.to_categories_excluded)
                )
            ]
            if not filtered_rows:
                continue

            text = "\n".join(
                f"from: {r.from_label.label if r.from_label else r.Transfer.from_address} | "
                f"to: {r.to_label.label if r.to_label else r.Transfer.to_address} | "
                f"value: {token.from_raw(r.Transfer.value):,.0f} | "
                f"etherscan: {_ETHERSCAN_URL_PREFIX}{r.Transfer.tx_hash}"
                for r in filtered_rows
            )
            notifications.append(Notification(sub.chat_id, text))
        return NotifyBatch(rows[-1].Transfer.block_number, notifications)


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
