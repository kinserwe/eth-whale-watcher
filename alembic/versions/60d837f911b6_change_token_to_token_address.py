"""change token to token_address

Revision ID: 60d837f911b6
Revises: a05392bf6475
Create Date: 2026-08-06 11:55:14.104319

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "60d837f911b6"
down_revision: Union[str, Sequence[str], None] = "a05392bf6475"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "transfer",
        "token",
        new_column_name="token_address",
        existing_type=sa.String(10),
        type_=sa.String(42),
        existing_nullable=False,
    )
    op.alter_column(
        "scan_state",
        "token",
        new_column_name="token_address",
        existing_type=sa.String(10),
        type_=sa.String(42),
        existing_nullable=False,
    )
    op.execute(
        "UPDATE transfer SET token_address = "
        "'0xdAC17F958D2ee523a2206206994597C13D831ec7' WHERE token_address = 'USDT'"
    )
    op.execute(
        "UPDATE scan_state SET token_address = "
        "'0xdAC17F958D2ee523a2206206994597C13D831ec7' WHERE token_address = 'USDT'"
    )
    op.create_index(op.f("ix_transfer_token_address"), "transfer", ["token_address"])


def downgrade() -> None:
    op.drop_index(op.f("ix_transfer_token_address"), "transfer")
    op.execute(
        "UPDATE transfer SET token_address = "
        "'USDT' WHERE token_address = '0xdAC17F958D2ee523a2206206994597C13D831ec7'"
    )
    op.execute(
        "UPDATE scan_state SET token_address = "
        "'USDT' WHERE token_address = '0xdAC17F958D2ee523a2206206994597C13D831ec7'"
    )
    op.alter_column(
        "transfer",
        "token_address",
        new_column_name="token",
        existing_type=sa.String(42),
        type_=sa.String(10),
        existing_nullable=False,
    )
    op.alter_column(
        "scan_state",
        "token_address",
        new_column_name="token",
        existing_type=sa.String(42),
        type_=sa.String(10),
        existing_nullable=False,
    )
