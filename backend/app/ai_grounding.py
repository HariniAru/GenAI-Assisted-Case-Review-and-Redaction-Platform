"""Build bounded generation context and resolve policy evidence on the server."""

import hashlib
import json
from dataclasses import dataclass

from langchain_core.documents import Document
from sqlalchemy.orm import Session

from app.models import ReferenceChunk
from app.reference_corpus import POLICY_HEADINGS, SOURCE, chunk_id
from app.reference_embeddings import model_key
from app.reference_service import IndexUnavailable
from app.schemas import PolicyReference

LABELS = {"PERSONAL_INFO", "CONFIDENTIAL", "PRIVILEGED", "HIGHLIGHT"}
MAX_CONTEXT_CHARS = 16000
MAX_DESCRIPTION_CHARS = 12000


@dataclass
class GroundingContext:
    text: str
    policies: dict[str, PolicyReference]


def policy_reference(document: Document, label: str) -> PolicyReference:
    section = f"1. {label}"
    if (
        label not in LABELS
        or document.id != chunk_id(section)
        or document.metadata.get("source") != SOURCE
        or document.metadata.get("kind") != "policy"
        or document.metadata.get("section") != section
    ):
        raise IndexUnavailable("Supporting policy is unavailable; re-ingest the reference corpus")
    body = document.page_content.split("\n", 1)[-1].strip()
    if not body:
        raise IndexUnavailable("Supporting policy is empty; re-ingest the reference corpus")
    excerpt = body if len(body) <= 360 else body[:357].rsplit(" ", 1)[0] + "…"
    return PolicyReference(
        chunk_id=document.id,
        content_sha256=hashlib.sha256(document.page_content.encode()).hexdigest(),
        section=section,
        excerpt=excerpt,
    )


def current_policy(db: Session, label: str) -> PolicyReference:
    row = db.get(ReferenceChunk, chunk_id(f"1. {label}"))
    if row is None or row.model_key != model_key():
        raise IndexUnavailable("Supporting policy is unavailable; re-ingest the reference corpus")
    return policy_reference(
        Document(id=row.id, page_content=row.content, metadata=row.chunk_metadata), label
    )


def build_grounding(documents: list[Document], activity_uid: str) -> GroundingContext:
    policies = {
        doc.metadata.get("section"): doc
        for doc in documents
        if doc.metadata.get("kind") == "policy"
    }
    required = {"1. " + heading for heading in POLICY_HEADINGS}
    if not required.issubset(policies):
        raise IndexUnavailable("Mandatory policies are missing; re-ingest the reference corpus")
    evidence = {label: policy_reference(policies[f"1. {label}"], label) for label in LABELS}
    selected = []

    def encode(doc: Document) -> str:
        return json.dumps(
            {
                "kind": doc.metadata["kind"],
                "section": doc.metadata["section"],
                "content": doc.page_content,
            },
            ensure_ascii=False,
        )

    # Mandatory rules are never truncated or dropped to make room for examples.
    for section in sorted(required):
        doc = policies[section]
        if doc.id != chunk_id(section) or doc.metadata.get("source") != SOURCE:
            raise IndexUnavailable("Mandatory policies are invalid; re-ingest the reference corpus")
        selected.append(encode(doc))
    used = sum(len(block) + 1 for block in selected)
    if used > MAX_CONTEXT_CHARS:
        raise IndexUnavailable("Mandatory policies exceed the generation context limit")
    examples = 0
    for kind in ("glossary", "example"):
        for doc in documents:
            if doc.metadata.get("kind") != kind or doc.metadata.get("source") != SOURCE:
                continue
            if kind == "example" and (
                doc.metadata.get("activity_uid") == activity_uid or examples >= 3
            ):
                continue
            block = encode(doc)
            if used + len(block) + 1 <= MAX_CONTEXT_CHARS:
                selected.append(block)
                used += len(block) + 1
                examples += int(kind == "example")
    return GroundingContext(text="\n".join(selected), policies=evidence)
