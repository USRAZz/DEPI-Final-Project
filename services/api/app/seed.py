"""Load the sample data into the database at DATABASE_URL.

    python -m app.seed                  # only into an empty database
    python -m app.seed --refresh-dates  # move sample payment requests back inside the gateway's 72 h window

Run `alembic upgrade head` first. Never point this at a database with real customer data.
"""

import argparse
import os
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import update
from sqlalchemy.orm import sessionmaker

from .db import PaymentRequestRow, make_engine
from .sql_store import SqlStore
from .store import seeded_store


def refresh_dates(engine) -> int:
    sample = seeded_store()
    now = datetime.now(UTC).replace(microsecond=0)
    with sessionmaker(engine).begin() as s:
        for rid, request in sample.payment_requests.items():
            age = request.created_at - sample.payment_requests[min(sample.payment_requests)].created_at
            s.execute(update(PaymentRequestRow).where(PaymentRequestRow.id == rid)
                      .values(created_at=now - timedelta(hours=6) + age))
    return len(sample.payment_requests)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--refresh-dates", action="store_true")
    args = parser.parse_args(argv)

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2
    engine = make_engine(url)
    if args.refresh_dates:
        print(f"refreshed {refresh_dates(engine)} sample payment requests")
        return 0
    store = SqlStore(engine)
    if not store.is_empty():
        print("database already has data; nothing loaded")
        return 0
    store.load(seeded_store())
    print("sample data loaded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
