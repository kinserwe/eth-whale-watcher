from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, echo=settings.sql_echo)

SessionFactory = sessionmaker(bind=engine)


class Base(DeclarativeBase): ...
