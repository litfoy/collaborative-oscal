from collections.abc import Callable

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.persistence.repositories import SQLAlchemyUnitOfWork


def create_session_factory() -> sessionmaker[Session]:
    engine = create_engine(get_settings().get_database_url(), pool_pre_ping=True)
    return sessionmaker(bind=engine, expire_on_commit=False)


def create_unit_of_work_factory() -> Callable[[], SQLAlchemyUnitOfWork]:
    session_factory = create_session_factory()
    return lambda: SQLAlchemyUnitOfWork(session_factory)
