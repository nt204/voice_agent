import argparse
import os
from pathlib import Path

from app.call_history import CallHistoryStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate SQLite call history to PostgreSQL.")
    parser.add_argument("--source", default="data/call_history.db")
    parser.add_argument("--target", default=os.getenv("DATABASE_URL", ""))
    args = parser.parse_args()
    if not args.target:
        parser.error("--target or DATABASE_URL is required")

    target = CallHistoryStore(args.target)
    counts = target.migrate_from_sqlite(Path(args.source))
    print(counts or "Target already contains call history; migration skipped.")


if __name__ == "__main__":
    main()
