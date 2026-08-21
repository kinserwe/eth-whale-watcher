from unittest.mock import patch

import pytest
from pydantic import PostgresDsn
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.database import Base
from app.models import AddressCategory, AddressLabel, AddressSource, ScanState, Subscriber, Transfer
from app.tokens import USDT

TEST_DATABASE_URL = str(
    PostgresDsn.build(
        scheme="postgresql+psycopg",
        username=settings.postgres_user,
        password=settings.postgres_password,
        host=settings.postgres_host,
        port=settings.postgres_port,
        path="whale_watcher_test",
    )
)


@pytest.fixture(scope="session")
def engine():
    engine = create_engine(TEST_DATABASE_URL, echo=settings.sql_echo)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def connection(engine):
    conn = engine.connect()
    outer = conn.begin()
    yield conn
    outer.rollback()
    conn.close()


@pytest.fixture
def db_session(connection):
    session = Session(bind=connection)
    yield session
    session.close()


@pytest.fixture(autouse=True)
def bound_session_factory(connection):
    factory = sessionmaker(bind=connection)
    with (
        patch("app.bot.notify.SessionFactory", factory),
        patch("app.bot.subscriptions.SessionFactory", factory),
    ):
        yield factory


@pytest.fixture
def make_transfer(db_session, fake_hash):
    def _make(
        block_number: int,
        *,
        log_index: int = 0,
        token_address: str = USDT.address,
        from_address: str = "0x" + "1" * 40,
        to_address: str = "0x" + "2" * 40,
    ) -> Transfer:
        transfer = Transfer(
            tx_hash=fake_hash(block_number * 1000 + log_index).to_0x_hex(),
            log_index=log_index,
            block_number=block_number,
            block_hash=fake_hash(block_number).to_0x_hex(),
            token_address=token_address,
            from_address=from_address,
            to_address=to_address,
            value=USDT.to_raw(1_000_000),
        )
        db_session.add(transfer)
        db_session.flush()
        return transfer

    return _make


@pytest.fixture
def make_subscriber(db_session):
    def _make(
        chat_id: int,
        last_notified_block: int,
        *,
        is_active: bool = True,
        from_categories_excluded: list[AddressCategory] | None = None,
        to_categories_excluded: list[AddressCategory] | None = None,
    ) -> Subscriber:
        if from_categories_excluded is None:
            from_categories_excluded = []

        if to_categories_excluded is None:
            to_categories_excluded = []

        sub = Subscriber(
            chat_id=chat_id,
            is_active=is_active,
            last_notified_block=last_notified_block,
            from_categories_excluded=from_categories_excluded,
            to_categories_excluded=to_categories_excluded,
        )
        db_session.add(sub)
        db_session.flush()
        return sub

    return _make


@pytest.fixture
def make_scan_state(db_session):
    def _make(last_scanned_block: int, *, token_address: str = USDT.address) -> ScanState:
        state = ScanState(
            token_address=token_address,
            last_scanned_block=last_scanned_block,
            last_scanned_hash=None,
        )
        db_session.add(state)
        db_session.flush()
        return state

    return _make


@pytest.fixture
def make_address_label(db_session):
    def _make(
        address: str,
        *,
        entity: str = "Test",
        label: str = "Test Label",
        category: AddressCategory = AddressCategory.EXCHANGE,
        source: AddressSource = AddressSource.INFERRED,
    ):
        label_ = AddressLabel(
            address=address, entity=entity, label=label, category=category, source=source
        )
        db_session.add(label_)
        db_session.flush()
        return label_

    return _make
