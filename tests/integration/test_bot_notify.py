from sqlalchemy import select

from app.bot.notify import _advance, _fetch, _skip_stale
from app.models import AddressCategory, Subscriber
from app.tokens import USDT, Token


class TestFetch:
    def test_returns_independent_transfers(self, make_scan_state, make_subscriber, make_transfer):
        make_scan_state(500)
        make_subscriber(1, 100)
        make_subscriber(2, 300)
        make_transfer(150)
        make_transfer(250)
        make_transfer(350)

        batch = _fetch(USDT)
        by_chat = {n.chat_id: n.text for n in batch.notifications}

        assert len(by_chat[1].splitlines()) == 3
        assert len(by_chat[2].splitlines()) == 1

    def test_returns_labelled(
        self,
        make_scan_state,
        make_subscriber,
        make_transfer,
        make_address_label,
    ):
        addr = "0x" + "3" * 40
        make_scan_state(500)
        make_subscriber(1, 100)
        make_transfer(150, from_address=addr)
        label = make_address_label(addr)

        batch = _fetch(USDT)
        assert len(batch.notifications) == 1
        assert f"from: {label.label}" in batch.notifications[0].text
        assert label.address not in batch.notifications[0].text

    def test_one_caught_up(self, make_scan_state, make_subscriber, make_transfer):
        make_scan_state(500)
        make_subscriber(1, 500)
        make_subscriber(2, 300)
        make_transfer(150)
        make_transfer(250)
        make_transfer(350)

        batch = _fetch(USDT)
        assert len(batch.notifications) == 1
        assert batch.notifications[0].chat_id == 2

    def test_excludes_above_head(self, make_scan_state, make_subscriber, make_transfer):
        make_scan_state(500)
        make_subscriber(1, 500)
        make_transfer(600)

        batch = _fetch(USDT)
        assert len(batch.notifications) == 0

    def test_excludes_another_token(self, make_scan_state, make_subscriber, make_transfer):
        another_token = Token("ANOTHER", "0x" + "a" * 40, 6)
        make_scan_state(500)
        make_scan_state(1000, token_address=another_token.address)
        make_subscriber(1, 300)
        make_transfer(400)
        make_transfer(500, token_address=another_token.address)

        batch = _fetch(USDT)

        assert len(batch.notifications[0].text.splitlines()) == 1
        assert batch.cursor == 400

    def test_excludes_inactive_subscribers(self, make_scan_state, make_subscriber, make_transfer):
        make_scan_state(500)
        make_subscriber(1, 400, is_active=False)
        make_transfer(450)

        batch = _fetch(USDT)
        assert len(batch.notifications) == 0

    def test_returns_correct_cursor(self, make_scan_state, make_subscriber, make_transfer):
        make_scan_state(500)
        make_subscriber(1, 300)
        make_transfer(450)

        batch = _fetch(USDT)
        assert batch.cursor == 450

    def test_returns_empty_if_no_state(self):
        batch = _fetch(USDT)
        assert batch.cursor == 0
        assert batch.notifications == []

    def test_returns_empty_if_no_subs(self, make_scan_state):
        make_scan_state(500)

        batch = _fetch(USDT)
        assert batch.cursor == 0
        assert batch.notifications == []

    def test_return_empty_if_no_transfers(self, make_scan_state, make_subscriber):
        make_scan_state(500)
        make_subscriber(1, 500)

        batch = _fetch(USDT)
        assert batch.cursor == 0
        assert batch.notifications == []

    def test_returns_limited_transfers(self, make_scan_state, make_subscriber, make_transfer):
        make_scan_state(500)
        make_subscriber(1, 0)
        for block in range(1, 52):
            make_transfer(block, log_index=block)

        batch = _fetch(USDT)

        assert len(batch.notifications[0].text.splitlines()) == 50
        assert batch.cursor == 50

    def test_excludes_from_label(
        self, make_scan_state, make_subscriber, make_transfer, make_address_label
    ):
        addr = "0x" + "3" * 40
        make_scan_state(500)
        make_subscriber(1, 300, from_categories_excluded=[AddressCategory.DEFI])
        make_subscriber(2, 300)
        make_transfer(400, from_address=addr)
        make_address_label(addr, category=AddressCategory.DEFI)

        batch = _fetch(USDT)

        assert len(batch.notifications) == 1
        assert batch.notifications[0].chat_id == 2

    def test_excludes_to_label(
        self, make_scan_state, make_subscriber, make_transfer, make_address_label
    ):
        addr = "0x" + "3" * 40
        make_scan_state(500)
        make_subscriber(1, 300)
        make_subscriber(2, 300, to_categories_excluded=[AddressCategory.EXCHANGE])
        make_transfer(400, to_address=addr)
        make_address_label(addr, category=AddressCategory.EXCHANGE)

        batch = _fetch(USDT)

        assert len(batch.notifications) == 1
        assert batch.notifications[0].chat_id == 1


class TestAdvance:
    def test_does_not_move_backwards(self, db_session, make_subscriber):
        make_subscriber(1, 900)
        _advance([1], 500)
        assert (
            db_session.execute(
                select(Subscriber.last_notified_block).where(Subscriber.chat_id == 1)
            ).scalar_one()
            == 900
        )

    def test_only_touches_listed_chats(self, db_session, make_subscriber):
        make_subscriber(1, 100)
        make_subscriber(2, 100)

        _advance([1], 500)

        assert (
            db_session.execute(
                select(Subscriber.last_notified_block).where(Subscriber.chat_id == 2)
            ).scalar_one()
            == 100
        )
        assert (
            db_session.execute(
                select(Subscriber.last_notified_block).where(Subscriber.chat_id == 1)
            ).scalar_one()
            == 500
        )


class TestSkipStale:
    def test_does_not_return_sub_on_threshold(self, db_session, make_subscriber, make_scan_state):
        make_scan_state(500)
        make_subscriber(1, 500)

        batch = _skip_stale(USDT)
        assert len(batch.notifications) == 0

    def test_cursor_unchanged(self, db_session, make_subscriber, make_scan_state, make_transfer):
        make_scan_state(4000)
        make_subscriber(1, 300)
        make_transfer(350)

        batch = _skip_stale(USDT)
        assert len(batch.notifications) == 1
        assert batch.notifications[0].text.startswith("Skipped 1 USDT")
        assert batch.cursor == 4000
        assert (
            db_session.execute(
                select(Subscriber.last_notified_block).where(Subscriber.chat_id == 1)
            ).scalar_one()
            == 300
        )
