from enum import StrEnum

from sqlalchemy import case, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import InstrumentedAttribute

from app.database import SessionFactory
from app.models import AddressCategory, ScanState, Subscriber
from app.tokens import USDT


class SubscribeResult(StrEnum):
    CREATED = "created"
    REACTIVATED = "reactivated"
    ALREADY_ACTIVE = "already_active"
    NOT_READY = "not_ready"


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
