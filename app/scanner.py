import logging
from collections.abc import Sequence

import requests
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from web3 import Web3
from web3.contract import Contract
from web3.exceptions import Web3Exception
from web3.types import EventData

from app.chain import get_block_hash, get_safe_block_head
from app.config import settings
from app.database import SessionFactory
from app.models import ScanState, Transfer
from app.tokens import Token

logger = logging.getLogger(__name__)

_REORG_REWIND_BLOCKS = 12
_TRANSFER_INSERT = (
    pg_insert(Transfer)
    .on_conflict_do_nothing(index_elements=[Transfer.tx_hash, Transfer.log_index])
    .returning(Transfer.tx_hash)
)


def _init_scan_state(session: Session, w3: Web3, token: Token) -> None:
    start = get_safe_block_head(w3)
    session.add(
        ScanState(
            token_address=token.address,
            last_scanned_block=start,
            last_scanned_hash=get_block_hash(w3, start),
        )
    )
    logger.info("initialized scan state for %s at block %s", token.symbol, start)


def _handle_reorg(session: Session, w3: Web3, token: Token, state: ScanState) -> bool:
    if not state.last_scanned_hash:
        return False

    node_hash = get_block_hash(w3, state.last_scanned_block)
    if node_hash == state.last_scanned_hash:
        return False

    rewind_to = max(state.last_scanned_block - _REORG_REWIND_BLOCKS, 0)
    deleted = session.execute(
        delete(Transfer).where(
            Transfer.token_address == token.address,
            Transfer.block_number > rewind_to,
        )
    ).rowcount
    logger.warning(
        "reorg detected at block %s, rewinding to %s, deleted %s",
        state.last_scanned_block,
        rewind_to,
        deleted,
    )
    state.last_scanned_block = rewind_to
    state.last_scanned_hash = get_block_hash(w3, rewind_to)
    return True


def _extract_whale_transfers(
    logs: Sequence[EventData], raw_threshold: int, token: Token
) -> list[dict]:
    return [
        {
            "tx_hash": log["transactionHash"].to_0x_hex(),
            "log_index": log["logIndex"],
            "block_number": log["blockNumber"],
            "block_hash": log["blockHash"].to_0x_hex(),
            "token_address": token.address,
            "from_address": log["args"]["from"],
            "to_address": log["args"]["to"],
            "value": log["args"]["value"],
        }
        for log in logs
        if log["args"]["value"] >= raw_threshold
    ]


def poll_contract(w3: Web3, contract: Contract, token: Token) -> None:
    try:
        with SessionFactory.begin() as session:
            state = session.execute(
                select(ScanState).where(ScanState.token_address == token.address).with_for_update()
            ).scalar_one_or_none()

            if state is None:
                _init_scan_state(session, w3, token)
                return

            if _handle_reorg(session, w3, token, state):
                return

            head = get_safe_block_head(w3)
            if head <= state.last_scanned_block:
                return

            to_block = min(head, state.last_scanned_block + settings.max_blocks_per_scan)
            logs = contract.events.Transfer.get_logs(
                from_block=state.last_scanned_block + 1, to_block=to_block
            )
            raw_threshold = token.to_raw(settings.whale_threshold_tokens)
            rows = _extract_whale_transfers(logs, raw_threshold, token)
            if rows:
                result = session.execute(_TRANSFER_INSERT, rows)
                inserted = len(result.all())
                largest = token.from_raw(max(r["value"] for r in rows))
                logger.info(
                    "inserted %s/%s transfers, largest %s", inserted, len(rows), f"{largest:,.0f}"
                )
            state.last_scanned_block = to_block
            state.last_scanned_hash = get_block_hash(w3, state.last_scanned_block)
    except requests.exceptions.RequestException as exc:
        body = exc.response.text[:200] if exc.response is not None else ""
        logger.warning("RPC request failed, skipping cycle: %s, %s", exc, body)
    except Web3Exception as exc:
        logger.warning("RPC error, skipping cycle: %s", exc)
    except SQLAlchemyError:
        logger.exception("database error during poll")
    except Exception:
        logger.exception("unexpected error during poll")
