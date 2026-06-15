"""SQLAlchemy database engine and session factory."""

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import config, PROJECT_ROOT


def _resolve_path(raw: str) -> str:
    """Resolve a relative path against the project root."""
    p = Path(raw)
    if p.is_absolute():
        return str(p)
    return str(PROJECT_ROOT / p)


DB_PATH = _resolve_path(config.storage.database_path)
DATABASE_URL = f"sqlite:///{DB_PATH}"

# Ensure the parent directory exists
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def get_db() -> Session:
    """Dependency injection for FastAPI — yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables defined by SQLAlchemy models."""
    from app.models import Base
    Base.metadata.create_all(bind=engine)
