from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.config import settings

sync_engine = create_engine(settings.database_url_sync, poolclass=NullPool, pool_pre_ping=True)
SyncSessionLocal = sessionmaker(bind=sync_engine, expire_on_commit=False)


@contextmanager
def get_sync_db():
    db: Session = SyncSessionLocal()
    try:
        yield db
    finally:
        db.close()
