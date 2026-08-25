import asyncio
import html
import logging
from dataclasses import dataclass

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import aliased

from app.database import SessionFactory
from app.models import AddressCategory, AddressLabel, ScanState, Subscriber, Transfer
from app.tokens import Token

_NOTIFY_INTERVAL_SECONDS = 30
_MAX_CATCHUP_BLOCKS = 3600
_MAX_SEND_ATTEMPTS = 3
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


def _short(address: str) -> str:
    return f"{address[:6]}…{address[-4:]}"


def _party(label: AddressLabel | None, address: str) -> str:
    if label is None:
        return f"<code>{_short(address)}</code>"
    return html.escape(label.label)


def _format(row, token: Token) -> str:
    transfer = row.Transfer
    return (
        f"🐋 <b>{token.from_raw(transfer.value):,.0f}</b> {token.symbol}\n"
        f"{_party(row.from_label, transfer.from_address)} → "
        f"{_party(row.to_label, transfer.to_address)}\n"
        f'<a href="{_ETHERSCAN_URL_PREFIX}{transfer.tx_hash}">view on etherscan</a>'
    )


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
        block_floor = min(sub.last_notified_block for sub in subs)
        threshold_floor = min(sub.token_threshold for sub in subs)
        from_alias = aliased(AddressLabel, name="from_label")
        to_alias = aliased(AddressLabel, name="to_label")
        rows = session.execute(
            select(Transfer, from_alias, to_alias)
            .outerjoin(from_alias, Transfer.from_address == from_alias.address)
            .outerjoin(to_alias, Transfer.to_address == to_alias.address)
            .where(
                Transfer.block_number > block_floor,
                Transfer.value >= threshold_floor,
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
                and r.Transfer.value >= token.to_raw(sub.token_threshold)
                and (
                    not _is_excluded(r.from_label, sub.from_categories_excluded)
                    and not _is_excluded(r.to_label, sub.to_categories_excluded)
                )
            ]
            if not filtered_rows:
                continue

            notifications.extend(
                Notification(sub.chat_id, _format(r, token)) for r in filtered_rows
            )
        return NotifyBatch(rows[-1].Transfer.block_number, notifications)


def _advance(chat_ids: set[int], new_cursor: int) -> None:
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
                    Transfer.value >= token.to_raw(sub.token_threshold),
                    Transfer.block_number > sub.last_notified_block,
                    Transfer.block_number <= head,
                    Transfer.token_address == token.address,
                )
            )
            notifications.append(
                Notification(
                    sub.chat_id,
                    f"Missed {missed:,} {token.symbol} alerts while you were away.",
                )
            )

        return NotifyBatch(head, notifications)


async def _send_one(bot: Bot, n: Notification) -> bool:
    for attempt in range(_MAX_SEND_ATTEMPTS):
        try:
            await bot.send_message(n.chat_id, n.text)
            return True
        except TelegramRetryAfter as exc:
            if attempt + 1 < _MAX_SEND_ATTEMPTS:
                await asyncio.sleep(exc.retry_after)
        except TelegramForbiddenError:
            await asyncio.to_thread(_deactivate, n.chat_id)
            return False
        except TelegramBadRequest as exc:
            if "chat not found" in exc.message:
                await asyncio.to_thread(_deactivate, n.chat_id)
            else:
                logger.exception("send failed for %s", n.chat_id)
            return False
        except Exception:
            logger.exception("send failed for %s", n.chat_id)
            return False
    logger.warning("gave up in %s after %d attempts", n.chat_id, _MAX_SEND_ATTEMPTS)
    return False


async def _send_batch(bot: Bot, batch: NotifyBatch) -> None:
    sent: set[int] = set()
    failed: set[int] = set()
    for n in batch.notifications:
        if await _send_one(bot, n):
            sent.add(n.chat_id)
        else:
            failed.add(n.chat_id)
    deliverable = sent - failed
    if deliverable:
        await asyncio.to_thread(_advance, deliverable, batch.cursor)


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
