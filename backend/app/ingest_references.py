"""Run with: uv run --env-file .env.postgres python -m app.ingest_references."""

import sys

from sqlalchemy.exc import SQLAlchemyError

from app.database import SessionLocal
from app.reference_corpus import CORPUS_PATH
from app.reference_embeddings import get_embeddings
from app.reference_service import ingest


def main() -> int:
    try:
        corpus = CORPUS_PATH.read_text(encoding="utf-8")
        with SessionLocal.begin() as session:
            counts = ingest(session, corpus, get_embeddings())
    except (SQLAlchemyError, OSError, ValueError, RuntimeError):
        # Do not print SQL parameters, source text, connection URLs, or credentials.
        print(
            "Reference ingestion failed; transaction rolled back. Check the corpus, "
            "migrations, database connection, and local embedding model availability.",
            file=sys.stderr,
        )
        return 1
    print(" ".join(f"{key}={value}" for key, value in counts.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
