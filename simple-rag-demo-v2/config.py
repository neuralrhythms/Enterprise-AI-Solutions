"""
config.py — Pipeline configuration constants for simple-rag-demo-v2.

Defines all tunable constants used across the ingestion and RAG pipeline
modules. No logic, no I/O beyond validate_config(). Import this module
to access shared configuration values.
"""

import os

# Groq API key — optional. When set, Groq is used for LLM generation instead
# of Ollama. Get a free key at https://console.groq.com — no credit card required.
# Leave unset (or empty) to keep using Ollama locally.
GROQ_API_KEY: str = os.environ.get("GROQ_API_KEY", "")

# Embedding and LLM models
EMBEDDING_MODEL: str = "BAAI/bge-base-en-v1.5"
OLLAMA_MODEL: str = os.environ.get("OLLAMA_MODEL", "llama3.2")

# BGE asymmetric prefixes
# BGE models are trained with separate instruction prefixes for queries vs passages.
# Omitting these degrades retrieval quality significantly.
BGE_QUERY_PREFIX: str = "Represent this sentence for searching relevant passages: "
BGE_PASSAGE_PREFIX: str = "Represent this passage for retrieval: "

# Directory paths
DOCUMENTS_DIR: str = "documents"
VECTORSTORE_DIR: str = "vectorstore"

# Timing log file path — one JSON line per query is appended here
TIMINGS_LOG_PATH: str = "logs/rag_timings.jsonl"

# Hierarchical chunking sizes
CHILD_CHUNK_SIZE: int = 400
CHILD_CHUNK_OVERLAP: int = 80
PARENT_CHUNK_SIZE: int = 1500

# Retrieval parameters
CANDIDATE_K: int = 20   # candidates fetched before re-ranking
TOP_K: int = 5          # top chunks passed to the LLM after re-ranking
MIN_SCORE: float = 0.30  # minimum FAISS cosine similarity to pass score filter


def validate_config() -> None:
    """
    Validates all pipeline configuration constants against their permitted ranges.

    Raises:
        ValueError: If any configuration value is outside its valid range, with
                    a message that includes the parameter name and valid range.
    """
    if not isinstance(CHILD_CHUNK_SIZE, int) or not (50 <= CHILD_CHUNK_SIZE <= 2000):
        raise ValueError(
            f"CHILD_CHUNK_SIZE must be an integer between 50 and 2000, got {CHILD_CHUNK_SIZE}"
        )

    max_overlap = CHILD_CHUNK_SIZE * 0.5
    if not isinstance(CHILD_CHUNK_OVERLAP, int) or not (0 <= CHILD_CHUNK_OVERLAP <= max_overlap):
        raise ValueError(
            f"CHILD_CHUNK_OVERLAP must be an integer between 0 and {int(max_overlap)} "
            f"(CHILD_CHUNK_SIZE * 0.5), got {CHILD_CHUNK_OVERLAP}"
        )

    if not isinstance(PARENT_CHUNK_SIZE, int) or not (200 <= PARENT_CHUNK_SIZE <= 10000):
        raise ValueError(
            f"PARENT_CHUNK_SIZE must be an integer between 200 and 10000, got {PARENT_CHUNK_SIZE}"
        )

    if PARENT_CHUNK_SIZE <= CHILD_CHUNK_SIZE:
        raise ValueError(
            f"PARENT_CHUNK_SIZE ({PARENT_CHUNK_SIZE}) must be greater than "
            f"CHILD_CHUNK_SIZE ({CHILD_CHUNK_SIZE})"
        )

    if not isinstance(CANDIDATE_K, int) or not (5 <= CANDIDATE_K <= 100):
        raise ValueError(
            f"CANDIDATE_K must be an integer between 5 and 100, got {CANDIDATE_K}"
        )

    if not isinstance(TOP_K, int) or not (1 <= TOP_K <= 20):
        raise ValueError(
            f"TOP_K must be an integer between 1 and 20, got {TOP_K}"
        )

    if TOP_K >= CANDIDATE_K:
        raise ValueError(
            f"TOP_K ({TOP_K}) must be less than CANDIDATE_K ({CANDIDATE_K})"
        )

    if not isinstance(MIN_SCORE, float) or not (0.0 <= MIN_SCORE <= 1.0):
        raise ValueError(
            f"MIN_SCORE must be a float between 0.0 and 1.0, got {MIN_SCORE}"
        )

    for name, value in [
        ("EMBEDDING_MODEL", EMBEDDING_MODEL),
        ("OLLAMA_MODEL", OLLAMA_MODEL),
        ("DOCUMENTS_DIR", DOCUMENTS_DIR),
        ("VECTORSTORE_DIR", VECTORSTORE_DIR),
        ("BGE_QUERY_PREFIX", BGE_QUERY_PREFIX),
        ("BGE_PASSAGE_PREFIX", BGE_PASSAGE_PREFIX),
        ("TIMINGS_LOG_PATH", TIMINGS_LOG_PATH),
    ]:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
