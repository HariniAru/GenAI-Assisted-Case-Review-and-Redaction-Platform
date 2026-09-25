"""Atomic corpus ingestion and a LangChain retriever backed by pgvector."""

import math
import re

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.retrievers import BaseRetriever
from sqlalchemy import delete, inspect, select, text
from sqlalchemy.orm import Session

from app.models import ReferenceChunk
from app.reference_corpus import POLICY_HEADINGS, SOURCE, chunk_id, parse_corpus
from app.reference_embeddings import model_key


class IndexUnavailable(ValueError):
    pass


def validate_vector(vector: list[float]) -> None:
    if len(vector) != 384 or not all(math.isfinite(float(value)) for value in vector):
        raise ValueError("Embedding must contain 384 finite values")
    if not any(vector):
        raise ValueError("Embedding must be nonzero")


def require_postgres(session: Session) -> None:
    if session.get_bind().dialect.name != "postgresql":
        raise IndexUnavailable("Reference retrieval requires PostgreSQL with pgvector")
    if not inspect(session.connection()).has_table("reference_chunks"):
        raise IndexUnavailable("Reference index is uninitialized; run migrations and ingestion")


def ingest(session: Session, corpus: str, embeddings: Embeddings) -> dict[str, int]:
    documents = parse_corpus(corpus)
    require_postgres(session)
    # Serialize ingestion for this corpus. Readers see the previous committed
    # version until all updates/deletions commit together.
    session.execute(text("SELECT pg_advisory_xact_lock(74201931)"))
    existing = {
        row.id: row
        for row in session.scalars(select(ReferenceChunk).where(ReferenceChunk.source == SOURCE))
    }
    changed = [
        doc
        for doc in documents
        if doc.id not in existing
        or (
            existing[doc.id].content != doc.page_content
            or existing[doc.id].chunk_metadata != doc.metadata
            or existing[doc.id].model_key != model_key()
        )
    ]
    vectors = embeddings.embed_documents([doc.page_content for doc in changed]) if changed else []
    if len(vectors) != len(changed):
        raise ValueError("Embedding count does not match chunk count")
    for vector in vectors:
        validate_vector(vector)
    for doc, vector in zip(changed, vectors, strict=True):
        row = existing.get(doc.id)
        if row is None:
            row = ReferenceChunk(id=doc.id, source=SOURCE)
            session.add(row)
        row.content = doc.page_content
        row.chunk_metadata = doc.metadata
        row.model_key = model_key()
        row.embedding = vector
    stale = set(existing) - {doc.id for doc in documents}
    if stale:
        session.execute(
            delete(ReferenceChunk).where(
                ReferenceChunk.source == SOURCE, ReferenceChunk.id.in_(stale)
            )
        )
    session.flush()
    return {"chunks": len(documents), "updated": len(changed), "removed": len(stale)}


class ReferenceRetriever(BaseRetriever):
    session: Session
    embeddings: Embeddings
    example_count: int = 3

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        require_postgres(self.session)
        rows = list(
            self.session.scalars(
                select(ReferenceChunk)
                .where(ReferenceChunk.source == SOURCE)
                .order_by(ReferenceChunk.id)
            )
        )
        required = {chunk_id("1. " + heading) for heading in POLICY_HEADINGS}
        policies = [row for row in rows if row.chunk_metadata["kind"] == "policy"]
        if (
            not required.issubset({row.id for row in policies})
            or not any(row.chunk_metadata["kind"] == "example" for row in rows)
            or any(row.model_key != model_key() for row in rows)
        ):
            raise IndexUnavailable(
                "Reference index is uninitialized or incompatible; run ingestion"
            )
        vector = self.embeddings.embed_query(query)
        validate_vector(vector)
        distance = ReferenceChunk.embedding.cosine_distance(vector)
        examples = self.session.execute(
            select(ReferenceChunk, distance.label("distance"))
            .where(
                ReferenceChunk.source == SOURCE,
                ReferenceChunk.chunk_metadata["kind"].as_string() == "example",
            )
            .order_by(distance, ReferenceChunk.id)
            .limit(self.example_count)
        ).all()
        matched = [
            row
            for row in rows
            if row.chunk_metadata["kind"] == "glossary"
            and re.search(
                r"(?<!\w)" + re.escape(row.chunk_metadata["term"]) + r"(?!\w)", query, re.IGNORECASE
            )
        ]
        documents = []
        for row in sorted(policies + matched, key=lambda row: row.chunk_metadata["section"]):
            method = "mandatory_policy" if row in policies else "exact_term"
            documents.append(
                Document(
                    id=row.id,
                    page_content=row.content,
                    metadata={**row.chunk_metadata, "retrieval": method},
                )
            )
        for row, score in examples:
            documents.append(
                Document(
                    id=row.id,
                    page_content=row.content,
                    metadata={
                        **row.chunk_metadata,
                        "retrieval": "semantic",
                        "cosine_distance": float(score),
                    },
                )
            )
        return documents
