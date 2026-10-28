from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from reviewer.config import get_settings


@lru_cache
def engine():
    url = get_settings().database_url
    args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, pool_pre_ping=True, connect_args=args)


def session():
    return sessionmaker(engine(), expire_on_commit=False)()
