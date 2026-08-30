from types import SimpleNamespace

from app.bot.notify import _extract_event
from app.models import AddressCategory, AddressLabel


class TestExtractEvent:
    def test_returns_event_for_known_pair(self):
        row = SimpleNamespace(
            from_label=AddressLabel(category=AddressCategory.EXCHANGE),
            to_label=AddressLabel(category=AddressCategory.TREASURY),
        )

        event = _extract_event(row)

        assert event == "Redemption"

    def test_returns_none_for_unknown_pair(self):
        row = SimpleNamespace(
            from_label=AddressLabel(category=AddressCategory.DEFI),
            to_label=AddressLabel(category=AddressCategory.MARKET_MAKER),
        )

        event = _extract_event(row)

        assert event is None

    def test_returns_empty_string_when_both_sides_unlabelled(self):
        row = SimpleNamespace(
            from_label=None,
            to_label=None,
        )

        event = _extract_event(row)

        assert event == ""
