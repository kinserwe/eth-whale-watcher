from unittest.mock import MagicMock, patch

from sqlalchemy import func, select

from app.models import ScanState, Transfer
from app.scanner import _TRANSFER_INSERT, _extract_whale_transfers, _handle_reorg
from app.tokens import USDT, Token

OTHER_TOKEN = Token(address="0x" + "a" * 40, decimals=6, symbol="OTHER")


def test_can_insert_and_read(db_session, make_transfer):
    make_transfer(100)
    assert db_session.scalar(select(func.count()).select_from(Transfer)) == 1


class TestHandleReorg:
    def test_reorg_deletes_only_rows_above_rewind(self, db_session, make_transfer):
        for block in [80, 85, 88, 90, 95]:
            make_transfer(block)
        make_transfer(95, log_index=1, token_address=OTHER_TOKEN.address)

        w3 = MagicMock()

        state = ScanState(
            token_address=USDT.address, last_scanned_block=100, last_scanned_hash="0xstale"
        )

        with patch("app.scanner.get_block_hash", side_effect=["0xcanonical", "0xrewind"]):
            assert _handle_reorg(db_session, w3, USDT, state) is True

        surviving = set(
            db_session.execute(select(Transfer.token_address, Transfer.block_number)).all()
        )
        assert surviving == {
            (USDT.address, 80),
            (USDT.address, 85),
            (USDT.address, 88),
            (OTHER_TOKEN.address, 95),
        }


class TestTransferInsert:
    def test_rescan_does_not_duplicate(self, db_session, make_transfer_log):
        threshold = USDT.to_raw(1_000_000)
        tx_seed = 7
        logs = [
            make_transfer_log(threshold, tx_seed=tx_seed),
            make_transfer_log(threshold, tx_seed=tx_seed, log_index=1),
        ]
        rows = _extract_whale_transfers(logs, threshold, USDT)

        first = db_session.execute(_TRANSFER_INSERT, rows).all()
        second = db_session.execute(_TRANSFER_INSERT, rows).all()

        assert len(first) == len(rows)
        assert len(second) == 0
        assert db_session.scalar(select(func.count()).select_from(Transfer)) == len(rows)
