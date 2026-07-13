# Spec: PostgreSQL call history and live dashboard refresh

## Objective

Store dashboard call history in PostgreSQL and make an open dashboard reflect inbound and outbound call changes without a manual reload.

## Tech Stack

- FastAPI and the existing synchronous call-history API
- SQLAlchemy Core for portable SQLite tests and PostgreSQL production access
- PostgreSQL 16 with psycopg 3
- Browser polling for reliable refresh without adding a second realtime protocol

## Commands

- Test: `python -m pytest -q`
- Build and run: `docker compose up --build -d`
- Inspect services: `docker compose ps`

## Project Structure

- `app/call_history.py`: portable call-history persistence
- `app/main.py`: database selection and existing dashboard APIs
- `app/static/dashboard.js`: automatic refresh lifecycle
- `scripts/migrate_call_history.py`: explicit SQLite-to-PostgreSQL migration
- `tests/`: persistence and dashboard refresh regression coverage

## Code Style

Use named SQL parameters and transaction-scoped connections:

```python
with engine.begin() as connection:
    connection.execute(text("SELECT * FROM calls WHERE id = :call_id"), {"call_id": call_id})
```

## Testing Strategy

- Keep fast behavior tests on temporary SQLite databases through the same SQLAlchemy implementation.
- Add a PostgreSQL integration smoke test in Docker after startup.
- Add static dashboard regression checks for polling, visibility refresh, and selected-detail refresh.

## Boundaries

- Always preserve the existing API response shape and use parameterized SQL.
- Always retain existing Docker SQLite history through a one-time migration when the PostgreSQL database is empty.
- Never commit database credentials from `.env`; Docker development credentials remain local defaults.
- Never clear an existing PostgreSQL database during application startup.

## Success Criteria

- Docker application connects to PostgreSQL and no longer creates or updates `call_history.db`.
- Existing call, transcript, analysis, order, and outbound-request behavior passes tests.
- Existing SQLite rows can be copied without duplicate call IDs.
- Dashboard refreshes every three seconds while visible, refreshes immediately on visibility/focus, and keeps the selected call detail current.
- PostgreSQL persists data across app container recreation.
