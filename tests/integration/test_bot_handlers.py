from sqlalchemy import func, select

from app.bot.handlers import SubscribeResult, subscribe, unsubscribe
from app.models import Subscriber


class TestSubscribe:
    def test_returns_not_ready(self, db_session):
        assert subscribe(1) == SubscribeResult.NOT_READY
        assert db_session.execute(select(func.count()).select_from(Subscriber)).scalar() == 0

    def test_returns_created(self, db_session, make_scan_state):
        chat_id = 1
        head = 500
        make_scan_state(head)
        assert subscribe(chat_id) == SubscribeResult.CREATED
        assert (
            db_session.execute(
                select(Subscriber.last_notified_block).where(Subscriber.chat_id == chat_id)
            ).scalar_one()
            == head
        )

    def test_returns_reactivated(self, db_session, make_scan_state, make_subscriber):
        chat_id = 1
        last_notified_block = 100
        head = 500
        make_scan_state(head)
        make_subscriber(chat_id, last_notified_block, is_active=False)
        assert subscribe(chat_id) == SubscribeResult.REACTIVATED
        assert (
            db_session.execute(
                select(Subscriber.last_notified_block).where(Subscriber.chat_id == chat_id)
            ).scalar_one()
            == head
        )
        assert (
            db_session.execute(
                select(Subscriber.is_active).where(Subscriber.chat_id == chat_id)
            ).scalar_one()
            is True
        )

    def test_returns_already_active(self, db_session, make_scan_state, make_subscriber):
        chat_id = 1
        last_notified_block = 100
        make_scan_state(500)
        make_subscriber(chat_id, last_notified_block)
        assert subscribe(chat_id) == SubscribeResult.ALREADY_ACTIVE
        assert (
            db_session.execute(
                select(Subscriber.last_notified_block).where(Subscriber.chat_id == chat_id)
            ).scalar_one()
            == last_notified_block
        )


class TestUnsubscribe:
    def test_sub_not_exist(self, db_session):
        unsubscribe(1)
        assert db_session.execute(select(func.count()).select_from(Subscriber)).scalar() == 0

    def test_made_sub_inactive(self, db_session, make_subscriber):
        chat_id = 1
        last_notified_block = 100
        make_subscriber(chat_id, last_notified_block)
        unsubscribe(chat_id)
        assert (
            db_session.execute(
                select(Subscriber.is_active).where(Subscriber.chat_id == chat_id)
            ).scalar_one()
            is False
        )
        assert (
            db_session.execute(
                select(Subscriber.last_notified_block).where(Subscriber.chat_id == chat_id)
            ).scalar_one()
            == last_notified_block
        )

    def test_stop_then_start_does_not_replay(self, db_session, make_scan_state, make_subscriber):
        chat_id = 1
        last_notified_block = 100
        head = 500
        make_scan_state(head)
        make_subscriber(chat_id, last_notified_block)

        unsubscribe(chat_id)
        assert subscribe(chat_id) == SubscribeResult.REACTIVATED
        assert (
            db_session.execute(
                select(Subscriber.last_notified_block).where(Subscriber.chat_id == chat_id)
            ).scalar_one()
            == head
        )
