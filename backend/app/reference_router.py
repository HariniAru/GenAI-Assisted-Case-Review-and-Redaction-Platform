from fastapi import APIRouter, Depends, HTTPException
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langsmith import tracing_context
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Activity
from app.reference_embeddings import get_embeddings
from app.reference_service import IndexUnavailable, ReferenceRetriever

router = APIRouter(tags=["references"])


def embedding_provider() -> Embeddings:
    # Lazy model loading: a missing activity or uninitialized index does not
    # require a model download. Also keeps ordinary API startup lightweight.
    class LazyEmbeddings(Embeddings):
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return get_embeddings().embed_documents(texts)

        def embed_query(self, text: str) -> list[float]:
            return get_embeddings().embed_query(text)

    return LazyEmbeddings()


@router.get("/activities/{activity_id}/references", response_model=list[Document])
def references(
    activity_id: int,
    db: Session = Depends(get_db),  # noqa: B008
    embeddings: Embeddings = Depends(embedding_provider),  # noqa: B008
) -> list[Document]:
    activity = db.get(Activity, activity_id)
    if activity is None:
        raise HTTPException(404, "Activity not found")
    try:
        retriever = ReferenceRetriever(
            session=db, embeddings=embeddings, example_count=get_settings().reference_examples
        )
        # Disable tracing even if the host has enabled LangSmith globally.
        with tracing_context(enabled=False):
            return retriever.invoke(activity.description)
    except IndexUnavailable as exc:
        raise HTTPException(503, str(exc)) from None
    except (SQLAlchemyError, OSError, ValueError, RuntimeError):
        raise HTTPException(
            503, "Reference retrieval unavailable; check database and local model"
        ) from None
