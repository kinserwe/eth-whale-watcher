from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import ARRAY, BigInteger, DateTime, Enum, Numeric, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AddressCategory(StrEnum):
    EXCHANGE = "exchange"
    BRIDGE = "bridge"
    TREASURY = "treasury"
    DEFI = "defi"
    MARKET_MAKER = "market_maker"


class AddressSource(StrEnum):
    VERIFIED = "verified"
    INFERRED = "inferred"
    DUNE = "dune"


AddressCategoryEnum = Enum(
    AddressCategory, name="address_category", values_callable=lambda e: [m.value for m in e]
)
AddressSourceEnum = Enum(
    AddressSource, name="address_source", values_callable=lambda e: [m.value for m in e]
)


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

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))
    last_notified_block: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    from_categories_excluded: Mapped[list[AddressCategory]] = mapped_column(
        ARRAY(AddressCategoryEnum), default=list, server_default="{}", nullable=False
    )
    to_categories_excluded: Mapped[list[AddressCategory]] = mapped_column(
        ARRAY(AddressCategoryEnum), default=list, server_default="{}", nullable=False
    )


class AddressLabel(Base):
    __tablename__ = "address_label"

    address: Mapped[str] = mapped_column(String(42), primary_key=True)
    entity: Mapped[str]
    label: Mapped[str]
    category: Mapped[AddressCategory] = mapped_column(AddressCategoryEnum)
    source: Mapped[AddressSource] = mapped_column(AddressSourceEnum)
