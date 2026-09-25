"""Local CPU embeddings exposed through LangChain's Embeddings interface."""

from functools import lru_cache

from langchain_core.embeddings import Embeddings

from app.config import get_settings


def model_key() -> str:
    settings = get_settings()
    return f"{settings.embedding_model}@{settings.embedding_revision}:384:window200-mean-v1"


class LocalEmbeddings(Embeddings):
    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer

        settings = get_settings()
        self.model = SentenceTransformer(
            settings.embedding_model,
            revision=settings.embedding_revision,
            device="cpu",
            trust_remote_code=False,
        )
        if self.model.get_sentence_embedding_dimension() != settings.embedding_dimensions:
            raise ValueError("Unexpected embedding dimensions")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        import numpy as np

        result = []
        for text in texts:
            tokens = self.model.tokenizer.encode(text, add_special_tokens=False, verbose=False)
            # Keep whole reference blocks in storage, but avoid silently truncating
            # their embeddings at MiniLM's 256-token input limit.
            windows = [
                self.model.tokenizer.decode(tokens[start : start + 200])
                for start in range(0, len(tokens), 200)
            ] or [""]
            vectors = self.model.encode(windows, normalize_embeddings=True, show_progress_bar=False)
            vector = np.mean(vectors, axis=0)
            vector /= max(float(np.linalg.norm(vector)), 1e-12)
            result.append(vector.tolist())
        return result

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


@lru_cache
def get_embeddings() -> Embeddings:
    return LocalEmbeddings()
