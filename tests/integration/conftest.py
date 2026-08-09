import pytest
from pydantic import PostgresDsn
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base
from app.models import Transfer
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


@pytest.fixture
def make_transfer(db_session, fake_hash):
    def _make(block_number: int, *, log_index: int = 0, token_address: str = USDT.address):
        transfer = Transfer(
            tx_hash=fake_hash(block_number * 1000 + log_index).to_0x_hex(),
            log_index=log_index,
            block_number=block_number,
            block_hash=fake_hash(block_number).to_0x_hex(),
            token_address=token_address,
            from_address="0x" + "1" * 40,
            to_address="0x" + "2" * 40,
            value=USDT.to_raw(1_000_000),
        )
        db_session.add(transfer)
        db_session.flush()
        return transfer

    return _make
