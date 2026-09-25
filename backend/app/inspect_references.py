"""Read-only, real-model sanity checks; these are not held-out evaluations."""

import json
import sys

from langsmith import tracing_context
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.database import SessionLocal
from app.models import Activity
from app.reference_embeddings import get_embeddings
from app.reference_service import ReferenceRetriever

SANITY_UIDS = ("ACT-1001-01", "ACT-1002-02", "ACT-1004-01", "ACT-1005-01", "ACT-1001-02")


def main() -> None:
    with SessionLocal() as session, tracing_context(enabled=False):
        retriever = ReferenceRetriever(
            session=session,
            embeddings=get_embeddings(),
            example_count=get_settings().reference_examples,
        )
        for uid in SANITY_UIDS:
            activity = session.scalar(select(Activity).where(Activity.activity_uid == uid))
            if activity is None:
                print(json.dumps({"activity_uid": uid, "error": "Activity not found"}))
                continue
            documents = retriever.invoke(activity.description)
            print(
                json.dumps(
                    {
                        "activity_uid": uid,
                        "activity_id": activity.id,
                        "references": [doc.metadata for doc in documents],
                    },
                    ensure_ascii=False,
                )
            )


if __name__ == "__main__":
    try:
        main()
    except (SQLAlchemyError, OSError, ValueError, RuntimeError):
        print(
            "Reference inspection failed; check migrations, ingestion, and local model availability.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
