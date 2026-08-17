import json
import logging
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert as pg_insert
from web3 import Web3

from app.database import SessionFactory
from app.logging_config import configure_logging
from app.models import AddressCategory, AddressLabel, AddressSource

_LABELS_PATH = Path(__file__).parent.parent / "labels.json"

logger = logging.getLogger(__name__)


def _load(path: Path):
    rows, seen = [], set()
    for entry in json.loads(path.read_text(encoding="utf-8")):
        address = Web3.to_checksum_address(entry["address"])
        if address in seen:
            raise ValueError(f"duplicate address: {address}")
        seen.add(address)
        rows.append(
            {
                "address": address,
                "entity": entry["entity"],
                "label": entry["label"],
                "category": AddressCategory(entry["category"]),
                "source": AddressSource(entry["source"]),
            }
        )
    return rows


def main():
    rows = _load(_LABELS_PATH)
    stmt = pg_insert(AddressLabel).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[AddressLabel.address],
        set_={
            "entity": stmt.excluded.entity,
            "label": stmt.excluded.label,
            "category": stmt.excluded.category,
            "source": stmt.excluded.source,
        },
    )
    with SessionFactory.begin() as session:
        session.execute(stmt)
    logger.info("loaded %s addresses", len(rows))


if __name__ == "__main__":
    configure_logging()
    main()
