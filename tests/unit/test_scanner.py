from unittest.mock import MagicMock, call, patch

import pytest
from sqlalchemy.orm import Session

from app.models import ScanState
from app.scanner import _extract_whale_transfers, _handle_reorg, _init_scan_state
from app.tokens import USDT


class TestExtractWhaleTransfers:
    def test_value_at_threshold_is_included(self, make_transfer_log):
        threshold = USDT.to_raw(1_000_000)
        logs = [make_transfer_log(threshold - 1), make_transfer_log(threshold, log_index=1)]

        rows = _extract_whale_transfers(logs, threshold, USDT)

        assert len(rows) == 1
        assert rows[0]["value"] == threshold

    def test_empty_logs_return_empty_rows(self):
        threshold = USDT.to_raw(1_000_000)
        logs = _extract_whale_transfers([], threshold, USDT)

        assert len(logs) == 0

    def test_zero_value_log_skipped(self, make_transfer_log):
        threshold = USDT.to_raw(1_000_000)
        logs = [make_transfer_log(0)]

        rows = _extract_whale_transfers(logs, threshold, USDT)

        assert len(rows) == 0

    def test_maps_log_fields_to_row(self, make_transfer_log, fake_hash):
        threshold = USDT.to_raw(1_000_000)
        logs = [make_transfer_log(threshold)]

        rows = _extract_whale_transfers(logs, threshold, USDT)

        assert len(rows) == 1
        row = rows[0]
        assert row == {
            "tx_hash": fake_hash(100 * 1000).to_0x_hex(),
            "log_index": 0,
            "block_number": 100,
            "block_hash": fake_hash(100).to_0x_hex(),
            "token_address": USDT.address,
            "from_address": "0x" + "1" * 40,
            "to_address": "0x" + "2" * 40,
            "value": threshold,
        }


class TestHandleReorg:
    @patch("app.scanner.get_block_hash", autospec=True)
    def test_no_stored_hash_skips_check(self, mock_get_block_hash):
        state = ScanState(
            token_address=USDT.address,
            last_scanned_block=100,
            last_scanned_hash=None,
        )
        w3 = MagicMock()
        session = MagicMock(spec=Session)

        assert _handle_reorg(session, w3, USDT, state) is False
        mock_get_block_hash.assert_not_called()
        session.execute.assert_not_called()
        assert state.last_scanned_block == 100

    @patch("app.scanner.get_block_hash", autospec=True)
    def test_matching_hash_is_not_a_reorg(self, mock_get_block_hash):
        state = ScanState(
            token_address=USDT.address,
            last_scanned_block=100,
            last_scanned_hash="0xtest",
        )
        w3 = MagicMock()
        session = MagicMock(spec=Session)
        mock_get_block_hash.return_value = "0xtest"

        assert _handle_reorg(session, w3, USDT, state) is False
        mock_get_block_hash.assert_called_once_with(w3, 100)
        session.execute.assert_not_called()
        assert state.last_scanned_block == 100
        assert state.last_scanned_hash == "0xtest"

    @pytest.mark.parametrize(
        ("last_scanned_block", "expected_rewind"),
        [(100, 88), (12, 0), (5, 0)],
    )
    @patch("app.scanner.get_block_hash", autospec=True)
    def test_hash_mismatch_rewinds_and_deletes(
        self, mock_get_block_hash, last_scanned_block, expected_rewind
    ):
        state = ScanState(
            token_address=USDT.address,
            last_scanned_block=last_scanned_block,
            last_scanned_hash="0xstale",
        )
        w3 = MagicMock()
        session = MagicMock(spec=Session)
        mock_get_block_hash.side_effect = ["0xcanonical", "0xrewind"]

        assert _handle_reorg(session, w3, USDT, state) is True
        assert mock_get_block_hash.call_args_list == [
            call(w3, last_scanned_block),
            call(w3, expected_rewind),
        ]
        session.execute.assert_called_once()
        assert state.last_scanned_block == expected_rewind
        assert state.last_scanned_hash == "0xrewind"


class TestInitScanState:
    @patch("app.scanner.get_block_hash", autospec=True)
    @patch("app.scanner.get_safe_block_head", autospec=True)
    def test_starts_at_safe_head(self, mock_head, mock_get_block_hash):
        expected_head = 500
        expected_hash = "0xstart"

        mock_head.return_value = expected_head
        mock_get_block_hash.return_value = expected_hash

        w3 = MagicMock()
        session = MagicMock(spec=Session)

        _init_scan_state(session, w3, USDT)

        session.add.assert_called_once()
        state = session.add.call_args.args[0]
        assert state.token_address == USDT.address
        assert state.last_scanned_block == expected_head
        assert state.last_scanned_hash == expected_hash
        mock_get_block_hash.assert_called_once_with(w3, expected_head)
