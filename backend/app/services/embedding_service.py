from fastembed import TextEmbedding

from app.core.config import get_settings


_embedding_model: TextEmbedding | None = None
_embedding_model_name: str | None = None
_embedding_dimension: int | None = None


def get_embedding_model() -> TextEmbedding:
    global _embedding_dimension, _embedding_model, _embedding_model_name

    model_name = get_settings().embedding_model_name

    if _embedding_model is None or _embedding_model_name != model_name:
        _embedding_model = TextEmbedding(model_name=model_name)
        _embedding_model_name = model_name
        _embedding_dimension = None

    return _embedding_model


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        raise ValueError("At least one text value is required for embedding.")

    safe_texts = [_safe_embedding_text(text) for text in texts]
    embeddings = get_embedding_model().embed(safe_texts)

    return [_vector_to_float_list(vector) for vector in embeddings]


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]


def get_embedding_dimension() -> int:
    global _embedding_dimension

    if _embedding_dimension is None:
        _embedding_dimension = len(embed_query("CreatorLens embedding health check."))

    return _embedding_dimension


def _safe_embedding_text(text: str) -> str:
    if isinstance(text, str) and text.strip():
        return text.strip()

    return "No text available."


def _vector_to_float_list(vector: object) -> list[float]:
    if hasattr(vector, "tolist"):
        values = vector.tolist()
    else:
        values = list(vector)  # type: ignore[arg-type]

    return [float(value) for value in values]
