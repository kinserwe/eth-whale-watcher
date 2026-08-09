from collections.abc import Callable
from typing import cast

import pytest
from hexbytes import HexBytes
from web3.datastructures import AttributeDict
from web3.types import EventData

from app.tokens import USDT

_FROM_ADDRESS = "0x" + "1" * 40
_TO_ADDRESS = "0x" + "2" * 40


def _fake_hash(seed: int) -> HexBytes:
    return HexBytes("0x" + f"{seed:x}".ljust(64, "0"))


@pytest.fixture
def fake_hash():
    return _fake_hash


@pytest.fixture
def make_transfer_log() -> Callable[..., EventData]:
    def _make(
        value: int,
        *,
        block_number: int = 100,
        log_index: int = 0,
        from_address: str = _FROM_ADDRESS,
        to_address: str = _TO_ADDRESS,
    ) -> EventData:
        return cast(
            EventData,
            AttributeDict(
                {
                    "address": USDT.address,
                    "args": AttributeDict(
                        {
                            "from": from_address,
                            "to": to_address,
                            "value": value,
                        }
                    ),
                    "event": "Transfer",
                    "logIndex": log_index,
                    "transactionIndex": 0,
                    "transactionHash": _fake_hash(block_number * 1000 + log_index),
                    "blockHash": _fake_hash(block_number),
                    "blockNumber": block_number,
                }
            ),
        )

    return _make
