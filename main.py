import logging
import time

import requests
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from web3 import Web3
from web3.exceptions import Web3Exception

from config import settings
from database import SessionFactory
from logging_config import configure_logging
from models import ScanState, Transfer
from tokens import USDT

_POLL_INTERVAL_SECONDS = 30
_TRANSFER_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "from", "type": "address"},
            {"indexed": True, "name": "to", "type": "address"},
            {"indexed": False, "name": "value", "type": "uint256"},
        ],
        "name": "Transfer",
        "type": "event",
    }
]
_TRANSFER_INSERT = (
    pg_insert(Transfer)
    .on_conflict_do_nothing(index_elements=[Transfer.tx_hash, Transfer.log_index])
    .returning(Transfer.tx_hash)
)

logger = logging.getLogger(__name__)

w3 = Web3(Web3.HTTPProvider(settings.eth_rpc_url))

checksum_address = w3.to_checksum_address(USDT.address)
contract = w3.eth.contract(address=checksum_address, abi=_TRANSFER_ABI)


def poll_contract() -> None:
    try:
        with SessionFactory.begin() as session:
            state = session.execute(
                select(ScanState).where(ScanState.token == USDT.symbol).with_for_update()
            ).scalar_one_or_none()

            if state is None:
                start = w3.eth.block_number - settings.confirmation_blocks
                session.add(ScanState(token=USDT.symbol, last_scanned_block=start))
                logger.info("initialized scan state for %s at block %s", USDT.symbol, start)
                return

            head = w3.eth.block_number - settings.confirmation_blocks
            if head <= state.last_scanned_block:
                return

            to_block = min(head, state.last_scanned_block + settings.max_blocks_per_scan)
            logs = contract.events.Transfer.get_logs(
                from_block=state.last_scanned_block + 1, to_block=to_block
            )
            raw_usdt = USDT.to_raw(settings.whale_threshold_tokens)
            rows = []
            for log in logs:
                if log["args"]["value"] >= raw_usdt:
                    rows.append(
                        {
                            "tx_hash": log["transactionHash"].to_0x_hex(),
                            "log_index": log["logIndex"],
                            "block_number": log["blockNumber"],
                            "block_hash": log["blockHash"].to_0x_hex(),
                            "token": USDT.symbol,
                            "from_address": log["args"]["from"],
                            "to_address": log["args"]["to"],
                            "value": log["args"]["value"],
                        }
                    )
            if rows:
                result = session.execute(_TRANSFER_INSERT, rows)
                inserted = len(result.all())
                largest = max(r["value"] for r in rows) / 10**USDT.decimals
                logger.info(
                    "inserted %s/%s transfers, largest %s", inserted, len(rows), f"{largest:,.0f}"
                )
            state.last_scanned_block = to_block
    except requests.exceptions.RequestException as exc:
        body = exc.response.text[:200] if exc.response is not None else ""
        logger.warning("RPC request failed, skipping cycle: %s, %s", exc, body)
    except Web3Exception as exc:
        logger.warning("RPC error, skipping cycle: %s", exc)
    except SQLAlchemyError:
        logger.exception("database error during poll")
    except Exception:
        logger.exception("unexpected error during poll")


def main():
    while True:
        poll_contract()
        time.sleep(_POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    configure_logging()
    main()
