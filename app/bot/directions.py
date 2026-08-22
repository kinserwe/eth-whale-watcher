from dataclasses import dataclass

from sqlalchemy.orm import InstrumentedAttribute

from app.models import Subscriber


@dataclass(frozen=True, eq=False)
class Direction:
    slug: str
    column: InstrumentedAttribute
    noun: str


FROM = Direction("from", Subscriber.from_categories_excluded, "sender")
TO = Direction("to", Subscriber.to_categories_excluded, "recipient")

DIRECTIONS = {d.slug: d for d in (FROM, TO)}
