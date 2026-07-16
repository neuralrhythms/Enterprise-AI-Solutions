"""
config.py — Pipeline configuration constants.

Defines all tunable constants used across the RAG pipeline modules.
No logic, no I/O. Import this module to access shared configuration values.

Constants:
    CHUNK_SIZE: Number of characters per text chunk.
    CHUNK_OVERLAP: Number of overlapping characters between consecutive chunks.
    TOP_K: Number of document chunks to retrieve for each question.
    EMBEDDING_MODEL: HuggingFace model name used to generate embeddings.
    OLLAMA_MODEL: Ollama model name used for answer generation.
    DOCUMENTS_DIR: Path to the directory containing source PDF files.
    VECTORSTORE_DIR: Path to the directory where the FAISS index is persisted.
"""

CHUNK_SIZE: int = 1000
CHUNK_OVERLAP: int = 200
TOP_K: int = 4
EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
OLLAMA_MODEL: str = "llama3.2"
DOCUMENTS_DIR: str = "documents"
VECTORSTORE_DIR: str = "vectorstore"


def validate_config() -> None:
    """
    Validates all pipeline configuration constants against their permitted ranges.

    Checks that integer constants fall within their required bounds and that
    string constants are non-empty. Intended to be called at entry-point startup
    (ingest.py __main__, app.py startup) before any pipeline work begins.

    Returns:
        None

    Raises:
        ValueError: If any configuration value is outside its valid range, with
                    a message that includes the parameter name and valid range.
    """
    if not isinstance(CHUNK_SIZE, int) or not (100 <= CHUNK_SIZE <= 10000):
        raise ValueError(
            f"CHUNK_SIZE must be an integer between 100 and 10000, got {CHUNK_SIZE}"
        )

    max_overlap = CHUNK_SIZE * 0.5
    if not isinstance(CHUNK_OVERLAP, int) or not (0 <= CHUNK_OVERLAP <= max_overlap):
        raise ValueError(
            f"CHUNK_OVERLAP must be an integer between 0 and {int(max_overlap)} "
            f"(CHUNK_SIZE * 0.5), got {CHUNK_OVERLAP}"
        )

    if not isinstance(TOP_K, int) or not (1 <= TOP_K <= 20):
        raise ValueError(
            f"TOP_K must be an integer between 1 and 20, got {TOP_K}"
        )

    for name, value in [
        ("EMBEDDING_MODEL", EMBEDDING_MODEL),
        ("OLLAMA_MODEL", OLLAMA_MODEL),
        ("DOCUMENTS_DIR", DOCUMENTS_DIR),
        ("VECTORSTORE_DIR", VECTORSTORE_DIR),
    ]:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
