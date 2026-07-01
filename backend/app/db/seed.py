"""Seeds the dev user and curated reference data. Run via `python -m app.db.seed`."""

from datetime import UTC, datetime

from sqlalchemy import select

from app.config import settings
from app.db.sync import get_sync_db
from app.models import Institution, Ticker, User

CURATED_TICKERS = [
    ("AAPL", "Apple Inc.", "Technology", "NASDAQ"),
    ("MSFT", "Microsoft Corporation", "Technology", "NASDAQ"),
    ("NVDA", "NVIDIA Corporation", "Technology", "NASDAQ"),
    ("GOOGL", "Alphabet Inc.", "Technology", "NASDAQ"),
    ("AMZN", "Amazon.com, Inc.", "Consumer Discretionary", "NASDAQ"),
    ("MU", "Micron Technology, Inc.", "Technology", "NASDAQ"),
]

# CIKs are SEC EDGAR's zero-padded 10-digit company identifiers.
CURATED_INSTITUTIONS = [
    ("Berkshire Hathaway Inc", "0001067983"),
    ("Bridgewater Associates, LP", "0001350694"),
    ("Renaissance Technologies LLC", "0001037389"),
]


def seed() -> None:
    with get_sync_db() as db:
        if not db.scalar(select(User).where(User.id == settings.dev_user_id)):
            db.add(User(id=settings.dev_user_id, email=settings.dev_user_email, created_at=datetime.now(UTC)))

        for symbol, name, sector, exchange in CURATED_TICKERS:
            if not db.scalar(select(Ticker).where(Ticker.symbol == symbol)):
                db.add(Ticker(symbol=symbol, name=name, sector=sector, exchange=exchange))

        for name, cik in CURATED_INSTITUTIONS:
            if not db.scalar(select(Institution).where(Institution.cik == cik)):
                db.add(Institution(name=name, cik=cik))

        db.commit()
        print("Seed complete.")


if __name__ == "__main__":
    seed()
