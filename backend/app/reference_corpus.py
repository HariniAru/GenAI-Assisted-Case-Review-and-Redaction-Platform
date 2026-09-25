"""Parse only reference sections, retaining complete labeled example blocks."""

import hashlib
import re
from pathlib import Path

from langchain_core.documents import Document

SOURCE = "docs/rag_reference_corpus.md"
CORPUS_PATH = Path(__file__).resolve().parents[2] / SOURCE
POLICY_HEADINGS = {
    "General rules",
    "PERSONAL_INFO",
    "CONFIDENTIAL",
    "PRIVILEGED",
    "HIGHLIGHT",
    "Ambiguity and scope",
}


def chunk_id(section: str) -> str:
    return hashlib.sha256(f"{SOURCE}:{section}".encode()).hexdigest()


def parse_corpus(text: str) -> list[Document]:
    sections = dict(re.findall(r"^## ([1-5])\. ([\s\S]*?)(?=^## |\Z)", text, re.MULTILINE))
    if not all(number in sections for number in ("1", "2", "3", "4")):
        raise ValueError("Corpus must contain Sections 1–4")
    documents = []

    def add(content: str, kind: str, section: str, **metadata: str) -> None:
        if not content.strip():
            raise ValueError("Empty reference block")
        documents.append(
            Document(
                id=chunk_id(section),
                page_content=content.strip(),
                metadata={
                    "source": SOURCE,
                    "kind": kind,
                    "section": section,
                    "status": "proposed",
                    **metadata,
                },
            )
        )

    policy = sections["1"].split("\n", 1)[1]
    intro, *blocks = re.split(r"^### ", policy, flags=re.MULTILINE)
    add(intro, "policy", "1. General rules")
    for block in blocks:
        heading = block.split("\n", 1)[0].strip()
        add("### " + block, "policy", "1. " + heading)
    if {doc.metadata["section"][3:] for doc in documents} != POLICY_HEADINGS:
        raise ValueError("Corpus policy headings are missing or unexpected")

    for line in sections["2"].splitlines():
        if not line.startswith("| "):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != 3 or cells[0] == "Term" or cells[0].startswith("---"):
            continue
        term = cells[0]
        add(line, "glossary", f"2. {term}", term=term)

    example_intro, *blocks = re.split(r"^### ", sections["3"], flags=re.MULTILINE)
    for block in blocks:
        heading = block.split("\n", 1)[0].strip()
        uid = re.match(r"ACT-\d+-\d+\b", heading)
        if not uid:
            raise ValueError("Example heading must start with an activity UID")
        status = "seed" if "Existing seed annotations:" in block else "proposed"
        add(
            example_intro + "\n### " + block,
            "example",
            "3. " + heading,
            activity_uid=uid[0],
            status=status,
        )
    add(sections["4"], "summary_guide", "4. Case summary style guide")
    if not blocks or not any(d.metadata["kind"] == "glossary" for d in documents):
        raise ValueError("Corpus examples or glossary are missing")
    if len({doc.id for doc in documents}) != len(documents):
        raise ValueError("Duplicate reference headings")
    return documents
