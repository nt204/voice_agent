from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.config import config


class Base(DeclarativeBase):
    pass


class CallRecordingRow(Base):
    __tablename__ = "call_recordings"

    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    call_id: Mapped[str] = mapped_column(String(160), index=True)
    stream_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    from_number: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    to_number: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    direction: Mapped[str] = mapped_column(String(40), default="inbound", index=True)
    sales_status: Mapped[str] = mapped_column(String(40), default="open", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="active", index=True)
    codec: Mapped[str | None] = mapped_column(String(40), nullable=True)
    sample_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    inbound_path: Mapped[str] = mapped_column(String(1024))
    outbound_path: Mapped[str] = mapped_column(String(1024))
    mixed_path: Mapped[str] = mapped_column(String(1024), default="")
    log_path: Mapped[str] = mapped_column(String(1024))
    inbound_bytes: Mapped[int] = mapped_column(Integer, default=0)
    outbound_bytes: Mapped[int] = mapped_column(Integer, default=0)
    mixed_bytes: Mapped[int] = mapped_column(Integer, default=0)
    log_bytes: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CallTranscriptRow(Base):
    __tablename__ = "call_transcripts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recording_id: Mapped[str | None] = mapped_column(
        String(160),
        ForeignKey("call_recordings.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    call_id: Mapped[str] = mapped_column(String(160), index=True)
    speaker: Mapped[str] = mapped_column(String(20), index=True)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class CallIntentRow(Base):
    __tablename__ = "call_intents"

    recording_id: Mapped[str] = mapped_column(
        String(160),
        ForeignKey("call_recordings.id", ondelete="CASCADE"),
        primary_key=True,
    )
    call_id: Mapped[str] = mapped_column(String(160), index=True)
    customer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    order_intent: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    product_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    combo: Mapped[str | None] = mapped_column(String(300), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    missing_fields: Mapped[str] = mapped_column(Text, default="[]")
    raw_json: Mapped[str] = mapped_column(Text, default="{}")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def _connect_args() -> dict:
    if config.database_url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


engine = create_engine(config.database_url, pool_pre_ping=True, connect_args=_connect_args())
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    if config.database_url.startswith("sqlite"):
        path = Path(config.database_url.removeprefix("sqlite:///"))
        if not path.is_absolute():
            path = Path(__file__).resolve().parent.parent / path
        path.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    _migrate_call_recordings()


def _migrate_call_recordings() -> None:
    inspector = inspect(engine)
    if "call_recordings" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("call_recordings")}
    additions = []
    if "direction" not in columns:
        additions.append(("direction", "VARCHAR(40)", "'inbound'"))
    if "sales_status" not in columns:
        additions.append(("sales_status", "VARCHAR(40)", "'open'"))
    if "mixed_path" not in columns:
        additions.append(("mixed_path", "VARCHAR(1024)", "''"))
    if "mixed_bytes" not in columns:
        additions.append(("mixed_bytes", "INTEGER", "0"))
    if not additions:
        return
    with engine.begin() as conn:
        for name, column_type, default in additions:
            conn.execute(text(f"ALTER TABLE call_recordings ADD COLUMN {name} {column_type} DEFAULT {default}"))


@contextmanager
def db_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
