"""
config.py — Pipeline configuration constants for simple-rag-demo-v3.

Defines all tunable constants used across the ingestion and RAG pipeline
modules. No logic, no I/O beyond validate_config(). Import this module
to access shared configuration values.

LLM provider: Groq (cloud, free tier) — https://console.groq.com
Groq replaces local Ollama. A GROQ_API_KEY is required to run the app.
"""

import os

# ---------------------------------------------------------------------------
# Groq LLM — required
# ---------------------------------------------------------------------------
# Get a free API key at https://console.groq.com — no credit card required.
GROQ_API_KEY: str = os.environ.get("GROQ_API_KEY", "")

# Groq model to use for answer generation.
# Recommended models (set via GROQ_MODEL environment variable):
#   llama-3.1-8b-instant   — fastest, recommended default
#   llama-3.3-70b-versatile — strongest quality
#   mixtral-8x7b-32768     — good for technical documents
GROQ_MODEL: str = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")

# ---------------------------------------------------------------------------
# Langfuse observability — optional
# ---------------------------------------------------------------------------
# Self-hosted (local Docker): docker compose up in the langfuse repo,
#   then set LANGFUSE_HOST=http://localhost:3000
# Cloud: sign up at cloud.langfuse.com (free tier available).
# Leave empty to run without tracing — the pipeline works unchanged.
LANGFUSE_PUBLIC_KEY: str = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY: str = os.environ.get("LANGFUSE_SECRET_KEY", "")
LANGFUSE_HOST: str = os.environ.get("LANGFUSE_HOST", "http://localhost:3000")

# ---------------------------------------------------------------------------
# Embedding model
# ---------------------------------------------------------------------------
EMBEDDING_MODEL: str = "BAAI/bge-base-en-v1.5"

# BGE asymmetric prefixes — required for correct retrieval quality.
BGE_QUERY_PREFIX: str = "Represent this sentence for searching relevant passages: "
BGE_PASSAGE_PREFIX: str = "Represent this passage for retrieval: "

# ---------------------------------------------------------------------------
# Storage paths
# ---------------------------------------------------------------------------
DOCUMENTS_DIR: str = "documents"
VECTORSTORE_DIR: str = "vectorstore"

# ---------------------------------------------------------------------------
# Hierarchical chunking sizes
# ---------------------------------------------------------------------------
CHILD_CHUNK_SIZE: int = 400
CHILD_CHUNK_OVERLAP: int = 80
PARENT_CHUNK_SIZE: int = 1500

# ---------------------------------------------------------------------------
# Retrieval parameters
# ---------------------------------------------------------------------------
CANDIDATE_K: int = 20   # candidates fetched before re-ranking
TOP_K: int = 5          # top chunks passed to the LLM after re-ranking
MIN_SCORE: float = 0.30  # minimum FAISS cosine similarity to pass score filter


def validate_config() -> None:
    """
    Validates all pipeline configuration constants against their permitted ranges.

    Raises:
        ValueError: If any configuration value is outside its valid range or
                    a required environment variable is not set.
    """
    # GROQ_API_KEY is required — fail fast with a clear message.
    if not GROQ_API_KEY:
        raise ValueError(
            "GROQ_API_KEY is not set. "
            "Get a free key at https://console.groq.com and set it as an "
            "environment variable before running the app."
        )

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
        ("GROQ_MODEL", GROQ_MODEL),
        ("DOCUMENTS_DIR", DOCUMENTS_DIR),
        ("VECTORSTORE_DIR", VECTORSTORE_DIR),
        ("BGE_QUERY_PREFIX", BGE_QUERY_PREFIX),
        ("BGE_PASSAGE_PREFIX", BGE_PASSAGE_PREFIX),
    ]:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
