from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, Numeric, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Transfer(Base):
    __tablename__ = "transfer"
    tx_hash: Mapped[str] = mapped_column(String(66), primary_key=True)
    log_index: Mapped[int] = mapped_column(primary_key=True)

    block_number: Mapped[int] = mapped_column(index=True)
    block_hash: Mapped[str] = mapped_column(String(66))

    token_address: Mapped[str] = mapped_column(String(42), index=True)
    from_address: Mapped[str] = mapped_column(String(42))
    to_address: Mapped[str] = mapped_column(String(42))
    value: Mapped[Decimal] = mapped_column(Numeric(78, 0))


class ScanState(Base):
    __tablename__ = "scan_state"

    token_address: Mapped[str] = mapped_column(String(42), primary_key=True)
    last_scanned_block: Mapped[int]
    last_scanned_hash: Mapped[str | None] = mapped_column(String(66), nullable=True)


class Subscriber(Base):
    __tablename__ = "subscriber"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))
    last_notified_block: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
