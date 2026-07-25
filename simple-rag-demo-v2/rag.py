"""
rag.py — Online retrieval and answer generation pipeline for simple-rag-demo-v2.

Implements the full query-time RAG pipeline:

1. Index loading: reads FAISS index, BM25 index, and chunk list from disk.
2. Query embedding: prepends BGE query prefix and encodes with BGE model.
3. Candidate retrieval: FAISS + BM25 hybrid search with RRF fusion,
   score threshold filtering, and MMR deduplication.
4. Re-ranking: cross-encoder scoring and top-K selection with parent
   content substitution.
5. Answer generation: Ollama LLM invocation with a structured prompt.

Primary entry point: answer_question(question: str) -> tuple[str, list, dict]
"""

import json
import logging
import pickle
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.llms import Ollama
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder

from config import (
    BGE_QUERY_PREFIX,
    CANDIDATE_K,
    EMBEDDING_MODEL,
    MIN_SCORE,
    OLLAMA_MODEL,
    TIMINGS_LOG_PATH,
    TOP_K,
    VECTORSTORE_DIR,
)
from prompts import RAG_PROMPT_TEMPLATE

logger = logging.getLogger(__name__)


# Ordered tuple of all timing span keys returned by answer_question().
# Used as the single source of truth for key order in logs, tables, and UI.
TIMING_KEYS = (
    "index_load_s",
    "bge_model_load_s",
    "query_embed_s",
    "faiss_search_s",
    "bm25_score_s",
    "rrf_mmr_s",
    "cross_encoder_load_s",
    "cross_encoder_rank_s",
    "llm_generate_s",
    "total_s",
)


def _write_timing_log(
    question: str,
    metrics: dict,
    status: str,
    error_type: str | None = None,
    error_message: str | None = None,
) -> None:
    """
    Append one JSON log entry to the JSONL timing log file.

    Creates the parent directory automatically if absent. Opens the file
    in append mode so entries from prior sessions are preserved. On any
    write failure, logs a warning and returns silently — the pipeline
    return value is unaffected.

    Args:
        question:      The user question string (truncated to 80 chars).
        metrics:       The Metrics Dict from answer_question().
        status:        "ok" on success, "error" on exception.
        error_type:    Exception class name, or None on success.
        error_message: Exception message string, or None on success.
    """
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "question": question[:80],
        **{key: metrics.get(key) for key in TIMING_KEYS},
        "status": status,
        "error_type": error_type,
        "error_message": error_message,
    }
    try:
        log_path = Path(TIMINGS_LOG_PATH)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(entry) + "\n")
    except Exception as write_exc:
        logger.warning("Failed to write timing log: %s", write_exc)


def _print_timing_table(metrics: dict) -> None:
    """
    Emit a human-readable timing table to the log at INFO level.

    Prints all ten timing stages in TIMING_KEYS order with aligned columns:
    stage name left-justified in a 26-character field, duration formatted
    to 4 decimal places.

    Args:
        metrics: The Metrics Dict returned by answer_question().
    """
    lines = ["Timing breakdown:"]
    for key in TIMING_KEYS:
        value = metrics.get(key)
        if value is not None:
            lines.append(f"  {key:<26}:  {value:.4f} s")
        else:
            lines.append(f"  {key:<26}:  —")
    logger.info("\n".join(lines))


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ScoredChunk:
    """
    A candidate chunk with associated retrieval scores and embedding.

    Attributes:
        document:    The LangChain Document containing page_content and metadata.
        faiss_score: Cosine similarity score from FAISS search; set to
                     negative infinity for chunks that entered only via BM25.
        rrf_score:   Reciprocal Rank Fusion score accumulated across FAISS
                     and BM25 ranked lists.
        embedding:   The document's vector representation used for MMR
                     diversity computation. Sourced from the raw FAISS index
                     (via `faiss_index.index.reconstruct`) when available;
                     falls back to the query embedding for BM25-only candidates.
    """

    document: Document
    faiss_score: float
    rrf_score: float
    embedding: np.ndarray


# ---------------------------------------------------------------------------
# Index loading
# ---------------------------------------------------------------------------

def load_index() -> tuple[FAISS, BM25Okapi, list[Document]]:
    """
    Load the persisted FAISS vector index, BM25 index, and child chunk list
    from the configured vectorstore directory.

    The expected on-disk layout is:
        VECTORSTORE_DIR/index.faiss   — FAISS binary index
        VECTORSTORE_DIR/bm25.pkl      — pickled BM25Okapi instance
        VECTORSTORE_DIR/chunks.pkl    — pickled list[Document]

    Returns:
        A three-tuple (faiss_index, bm25_index, chunks).

    Raises:
        FileNotFoundError: If ``VECTORSTORE_DIR/index.faiss`` does not exist,
            indicating that the ingestion pipeline has not yet been run.
    """
    vectorstore_path = Path(VECTORSTORE_DIR)
    index_file = vectorstore_path / "index.faiss"

    if not index_file.exists():
        raise FileNotFoundError("Vector store not found. Run ingest.py first.")

    # Initialise the same embeddings model used during ingestion so LangChain
    # can reconstruct the FAISS wrapper correctly.
    embeddings = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL,
        model_kwargs={"device": "cpu"},
    )

    faiss_index = FAISS.load_local(
        str(vectorstore_path),
        embeddings,
        allow_dangerous_deserialization=True,
    )

    bm25_path = vectorstore_path / "bm25.pkl"
    with open(bm25_path, "rb") as bm25_file:
        bm25_index: BM25Okapi = pickle.load(bm25_file)

    chunks_path = vectorstore_path / "chunks.pkl"
    with open(chunks_path, "rb") as chunks_file:
        chunks: list[Document] = pickle.load(chunks_file)

    return faiss_index, bm25_index, chunks


# ---------------------------------------------------------------------------
# Query embedding
# ---------------------------------------------------------------------------

def embed_query(question: str) -> np.ndarray:
    """
    Encode a user question into a dense vector using the BGE embedding model.

    The BGE model is trained with an asymmetric instruction scheme: queries
    must be prefixed with ``BGE_QUERY_PREFIX`` to achieve the best retrieval
    quality against passage-prefixed document embeddings.

    Args:
        question: The raw user question string (without any prefix).

    Returns:
        A 1-D ``np.ndarray`` of floats representing the query embedding.
    """
    embeddings = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL,
        model_kwargs={"device": "cpu"},
    )
    # The prefix is prepended manually so the logic is explicit and testable.
    prefixed_question = BGE_QUERY_PREFIX + question
    query_vector = embeddings.embed_query(prefixed_question)
    return np.array(query_vector, dtype=np.float32)


# ---------------------------------------------------------------------------
# Candidate retrieval
# ---------------------------------------------------------------------------

def _chunk_key(document: Document) -> str:
    """
    Derive a stable identity key for a Document used during RRF deduplication.

    Uses page_content combined with the ``source`` metadata field so that
    two Document objects wrapping the same chunk are treated as identical even
    if they arrive from different ranked lists.

    Args:
        document: The Document to key.

    Returns:
        A string key unique to the chunk's content and source.
    """
    source = document.metadata.get("source", "")
    return f"{source}::{document.page_content}"


def _cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    """
    Compute the cosine similarity between two 1-D vectors.

    Args:
        vec_a: First vector.
        vec_b: Second vector.

    Returns:
        A float in [-1, 1].  Returns 0.0 if either vector has zero norm.
    """
    norm_a = np.linalg.norm(vec_a)
    norm_b = np.linalg.norm(vec_b)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(vec_a, vec_b) / (norm_a * norm_b))


def retrieve_candidates(
    faiss_index: FAISS,
    bm25_index: BM25Okapi,
    chunks: list[Document],
    query_embedding: np.ndarray,
    question: str,
    faiss_results: list[tuple[Document, float]] | None = None,
    top_bm25_indices: np.ndarray | None = None,
) -> list[ScoredChunk]:
    """
    Retrieve and fuse candidate chunks from the FAISS and BM25 indexes.

    Pipeline steps:
    1. FAISS search — top ``CANDIDATE_K`` chunks by cosine similarity.
    2. BM25 search  — top ``CANDIDATE_K`` chunks by BM25 score.
    3. RRF fusion   — merge both ranked lists; each rank ``r`` (0-indexed)
       contributes ``1 / (r + 60)`` to the chunk's running RRF score.
    4. Score filter — discard candidates whose FAISS similarity score is
       strictly below ``MIN_SCORE``.
    5. MMR          — select up to ``CANDIDATE_K`` diverse candidates from
       the filtered list using Maximal Marginal Relevance (lambda = 0.5).

    Args:
        faiss_index:       LangChain FAISS wrapper loaded from disk.
        bm25_index:        BM25Okapi instance loaded from disk.
        chunks:            Full list of child Document objects (corpus order).
        query_embedding:   Dense query vector from ``embed_query()``.
        question:          Raw user question string (used for BM25 tokenisation).
        faiss_results:     Pre-computed FAISS results (allows answer_question to
                           time FAISS separately). If None, computed internally.
        top_bm25_indices:  Pre-computed BM25 top indices (allows answer_question
                           to time BM25 separately). If None, computed internally.

    Returns:
        A list of ``ScoredChunk`` objects — the MMR-selected diverse candidates.

    Raises:
        RuntimeError: If no candidates remain after the MIN_SCORE filter.
    """
    # Use pre-computed results if provided (allows answer_question to time
    # FAISS and BM25 separately before calling this function for RRF+MMR).
    if faiss_results is None:
        faiss_results = faiss_index.similarity_search_with_relevance_scores(
            question, k=CANDIDATE_K
        )

    if top_bm25_indices is None:
        tokenised_query = question.split()
        bm25_scores_arr: np.ndarray = bm25_index.get_scores(tokenised_query)
        top_bm25_indices = np.argsort(bm25_scores_arr)[::-1][:CANDIDATE_K]

    # ------------------------------------------------------------------
    # Step 3: RRF fusion
    # ------------------------------------------------------------------
    # Accumulate per-chunk RRF scores and FAISS scores in a single pass.
    # Key → (Document, rrf_score, faiss_score)
    rrf_accumulator: dict[str, list] = {}

    for rank, (doc, faiss_score) in enumerate(faiss_results):
        key = _chunk_key(doc)
        rrf_contribution = 1.0 / (rank + 60)
        if key not in rrf_accumulator:
            rrf_accumulator[key] = [doc, rrf_contribution, faiss_score]
        else:
            rrf_accumulator[key][1] += rrf_contribution
            # Keep the FAISS score — it is already set from the FAISS list

    for rank, corpus_index in enumerate(top_bm25_indices):
        bm25_doc = chunks[corpus_index]
        key = _chunk_key(bm25_doc)
        rrf_contribution = 1.0 / (rank + 60)
        if key not in rrf_accumulator:
            # BM25-only candidate; FAISS score is unknown → use -inf
            rrf_accumulator[key] = [bm25_doc, rrf_contribution, float("-inf")]
        else:
            rrf_accumulator[key][1] += rrf_contribution
            # FAISS score already present from the FAISS pass above

    # Sort merged list descending by RRF score.
    merged: list[tuple[Document, float, float]] = [
        (entry[0], entry[1], entry[2])
        for entry in sorted(
            rrf_accumulator.values(), key=lambda e: e[1], reverse=True
        )
    ]

    # ------------------------------------------------------------------
    # Step 4: Score filter — remove sub-threshold candidates
    # ------------------------------------------------------------------
    filtered: list[tuple[Document, float, float]] = [
        (doc, rrf_score, faiss_score)
        for doc, rrf_score, faiss_score in merged
        if faiss_score >= MIN_SCORE
    ]

    if not filtered:
        raise RuntimeError(
            "No relevant chunks found above the minimum similarity threshold."
        )

    # ------------------------------------------------------------------
    # Step 5: Retrieve per-document embeddings for MMR
    # ------------------------------------------------------------------
    # LangChain's FAISS wrapper exposes the raw faiss.Index via .index and
    # the mapping from position to docstore ID via .index_to_docstore_id.
    # We can reconstruct the stored vector for any position with .reconstruct().
    # Build a lookup: docstore_id → raw embedding vector.
    faiss_raw_index = faiss_index.index
    id_to_vector: dict[str, np.ndarray] = {}
    for position, docstore_id in faiss_index.index_to_docstore_id.items():
        try:
            vector = faiss_raw_index.reconstruct(position)
            id_to_vector[docstore_id] = np.array(vector, dtype=np.float32)
        except Exception:
            # reconstruct is not supported on all FAISS index types (e.g.
            # IndexFlat without add_with_ids).  Fall through to query fallback.
            pass

    # Build a reverse lookup: page_content+source → docstore_id, so we can
    # match filtered chunks back to their stored vectors.
    docstore_key_to_id: dict[str, str] = {}
    for docstore_id, stored_doc in faiss_index.docstore._dict.items():
        docstore_key_to_id[_chunk_key(stored_doc)] = docstore_id

    def _get_embedding(doc: Document) -> np.ndarray:
        """Return the stored FAISS vector for doc, or fall back to query_embedding."""
        chunk_key = _chunk_key(doc)
        docstore_id = docstore_key_to_id.get(chunk_key)
        if docstore_id is not None:
            vector = id_to_vector.get(docstore_id)
            if vector is not None:
                return vector
        # Fallback: use the query embedding for BM25-only or unresolvable candidates.
        # MMR will still deduplicate identical chunks; diversity selection degrades
        # gracefully to relevance-only ordering for these candidates.
        return query_embedding

    # ------------------------------------------------------------------
    # Step 6: MMR — select up to CANDIDATE_K diverse candidates
    # ------------------------------------------------------------------
    # lambda = 0.5 balances relevance and diversity equally.
    mmr_lambda = 0.5

    # Seed the candidate pool with ScoredChunk objects.
    candidate_pool: list[ScoredChunk] = [
        ScoredChunk(
            document=doc,
            faiss_score=faiss_score,
            rrf_score=rrf_score,
            embedding=_get_embedding(doc),
        )
        for doc, rrf_score, faiss_score in filtered
    ]

    selected: list[ScoredChunk] = []
    remaining: list[ScoredChunk] = list(candidate_pool)

    while remaining and len(selected) < CANDIDATE_K:
        if not selected:
            # First pick: choose the highest-relevance candidate.
            best_index = int(
                np.argmax([c.faiss_score if c.faiss_score > float("-inf") else c.rrf_score
                           for c in remaining])
            )
        else:
            # Subsequent picks: maximise MMR score.
            selected_embeddings = [s.embedding for s in selected]
            best_index = -1
            best_mmr_score = float("-inf")

            for i, candidate in enumerate(remaining):
                # Relevance: prefer FAISS score; fall back to RRF score for
                # BM25-only candidates (RRF is a relative rank signal, so it
                # serves as a proxy when FAISS score is unavailable).
                relevance = (
                    candidate.faiss_score
                    if candidate.faiss_score > float("-inf")
                    else candidate.rrf_score
                )
                # Diversity penalty: maximum cosine similarity to any already
                # selected chunk.
                max_sim_to_selected = max(
                    _cosine_similarity(candidate.embedding, sel_emb)
                    for sel_emb in selected_embeddings
                )
                mmr_score = (
                    mmr_lambda * relevance
                    - (1.0 - mmr_lambda) * max_sim_to_selected
                )
                if mmr_score > best_mmr_score:
                    best_mmr_score = mmr_score
                    best_index = i

        selected.append(remaining.pop(best_index))

    return selected


# ---------------------------------------------------------------------------
# Re-ranking
# ---------------------------------------------------------------------------

def rerank(candidates: list[ScoredChunk], question: str, cross_encoder: CrossEncoder) -> list[Document]:
    """
    Re-rank candidate chunks using a pre-built cross-encoder model and return
    the top TOP_K chunks with parent content substituted.

    The cross-encoder scores each (question, chunk_text) pair jointly, which is
    more accurate than the bi-encoder similarity used during retrieval. After
    sorting, each selected child chunk's page_content is replaced with its full
    parent_content so the LLM receives broader context.

    Args:
        candidates:    MMR-selected ScoredChunk objects from retrieve_candidates().
        question:      The raw user question string.
        cross_encoder: A pre-instantiated CrossEncoder model instance.

    Returns:
        A list of at most TOP_K LangChain Document objects, each with:
        - page_content set to the parent_content value
        - metadata["rerank_score"] set to the float cross-encoder score
    """
    # Build (query, passage) pairs for the cross-encoder.
    pairs = [(question, candidate.document.page_content) for candidate in candidates]
    scores = cross_encoder.predict(pairs)

    # Sort candidates descending by cross-encoder score.
    scored_candidates = sorted(
        zip(scores, candidates), key=lambda item: item[0], reverse=True
    )

    # Take top TOP_K and substitute parent content.
    reranked_documents: list[Document] = []
    for score, scored_chunk in scored_candidates[:TOP_K]:
        scored_chunk.document.page_content = scored_chunk.document.metadata["parent_content"]
        scored_chunk.document.metadata["rerank_score"] = float(score)
        reranked_documents.append(scored_chunk.document)

    return reranked_documents


# ---------------------------------------------------------------------------
# Answer generation
# ---------------------------------------------------------------------------

def generate_answer(context: str, question: str) -> str:
    """
    Generate an answer from the LLM using the structured RAG prompt.

    Builds the prompt from RAG_PROMPT_TEMPLATE, invokes the locally running
    Ollama model, and returns the answer string. If Ollama is unreachable or
    times out, a ConnectionError is raised with an actionable message.

    Args:
        context:  The concatenated parent chunk text to use as context.
        question: The raw user question string.

    Returns:
        The answer string produced by the LLM.

    Raises:
        ConnectionError: If Ollama cannot be reached or does not respond in time.
    """
    prompt = RAG_PROMPT_TEMPLATE.format(context=context, question=question)

    try:
        llm = Ollama(model=OLLAMA_MODEL, timeout=60)
        answer = llm.invoke(prompt)
    except ConnectionError:
        raise ConnectionError(
            "Ollama is unavailable. Ensure it is running at localhost:11434."
        )
    except TimeoutError:
        raise ConnectionError(
            "Ollama is unavailable. Ensure it is running at localhost:11434."
        )
    except Exception as exc:
        if "connection" in str(exc).lower():
            raise ConnectionError(
                "Ollama is unavailable. Ensure it is running at localhost:11434."
            )
        raise

    return answer


# ---------------------------------------------------------------------------
# Primary entry point
# ---------------------------------------------------------------------------

def answer_question(question: str) -> tuple[str, list[Document], dict]:
    """
    Run the full RAG pipeline for a user question and return the answer,
    source chunks, and granular timing metrics.

    Times each of the ten pipeline stages individually using time.monotonic().
    Persists a structured log entry to TIMINGS_LOG_PATH after every call,
    whether the call succeeds or raises an exception.

    Args:
        question: The raw user question string.

    Returns:
        A three-tuple:
        - answer (str): The LLM-generated answer.
        - reranked_chunks (list[Document]): TOP_K documents with parent content
          and rerank_score metadata, used by the UI to render sidebar cards.
        - metrics (dict): Ten timing keys from TIMING_KEYS, each a float (seconds,
          rounded to 4 decimal places) or None if the stage did not complete.

    Raises:
        ValueError:        If question is empty or whitespace-only.
        FileNotFoundError: If the vector store has not been built yet.
        RuntimeError:      If no candidates pass the MIN_SCORE filter, or if a
                           required model is not found in the local cache.
        ConnectionError:   If Ollama is unreachable or times out.
    """
    if not question or not question.strip():
        raise ValueError("Please enter a question before submitting.")

    t_total = time.monotonic()
    metrics: dict = {k: None for k in TIMING_KEYS}

    try:
        # ------------------------------------------------------------------
        # Stage 1: Index loading
        # ------------------------------------------------------------------
        t0 = time.monotonic()
        faiss_index, bm25_index, chunks = load_index()
        metrics["index_load_s"] = round(time.monotonic() - t0, 4)

        # ------------------------------------------------------------------
        # Stage 2: BGE model load
        # ------------------------------------------------------------------
        t0 = time.monotonic()
        embeddings = HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL,
            model_kwargs={"device": "cpu"},
        )
        metrics["bge_model_load_s"] = round(time.monotonic() - t0, 4)

        # ------------------------------------------------------------------
        # Stage 3: Query embedding
        # ------------------------------------------------------------------
        t0 = time.monotonic()
        prefixed_question = BGE_QUERY_PREFIX + question
        query_embedding = np.array(
            embeddings.embed_query(prefixed_question), dtype=np.float32
        )
        metrics["query_embed_s"] = round(time.monotonic() - t0, 4)

        # ------------------------------------------------------------------
        # Stage 4: FAISS search
        # ------------------------------------------------------------------
        t0 = time.monotonic()
        faiss_results: list[tuple[Document, float]] = (
            faiss_index.similarity_search_with_relevance_scores(question, k=CANDIDATE_K)
        )
        metrics["faiss_search_s"] = round(time.monotonic() - t0, 4)

        # ------------------------------------------------------------------
        # Stage 5: BM25 scoring
        # ------------------------------------------------------------------
        t0 = time.monotonic()
        tokenised_query = question.split()
        bm25_scores: np.ndarray = bm25_index.get_scores(tokenised_query)
        top_bm25_indices = np.argsort(bm25_scores)[::-1][:CANDIDATE_K]
        metrics["bm25_score_s"] = round(time.monotonic() - t0, 4)

        # ------------------------------------------------------------------
        # Stage 6: RRF fusion + score filter + MMR
        # ------------------------------------------------------------------
        t0 = time.monotonic()
        candidates = retrieve_candidates(
            faiss_index, bm25_index, chunks, query_embedding, question,
            faiss_results=faiss_results,
            top_bm25_indices=top_bm25_indices,
        )
        metrics["rrf_mmr_s"] = round(time.monotonic() - t0, 4)

        # ------------------------------------------------------------------
        # Stage 7: Cross-encoder model load
        # ------------------------------------------------------------------
        t0 = time.monotonic()
        cross_encoder_model_name = "cross-encoder/ms-marco-MiniLM-L-6-v2"
        try:
            cross_encoder = CrossEncoder(cross_encoder_model_name, device="cpu")
        except (OSError, IOError):
            raise RuntimeError(
                f"Model '{cross_encoder_model_name}' not found in cache. "
                f"Download with: pip install sentence-transformers "
                f"then run: python -c \"from sentence_transformers import CrossEncoder; "
                f"CrossEncoder('{cross_encoder_model_name}')\""
            )
        metrics["cross_encoder_load_s"] = round(time.monotonic() - t0, 4)

        # ------------------------------------------------------------------
        # Stage 8: Cross-encoder re-ranking
        # ------------------------------------------------------------------
        t0 = time.monotonic()
        reranked_chunks = rerank(candidates, question, cross_encoder)
        metrics["cross_encoder_rank_s"] = round(time.monotonic() - t0, 4)

        # ------------------------------------------------------------------
        # Stage 9: LLM generation
        # ------------------------------------------------------------------
        t0 = time.monotonic()
        context = "\n\n".join(chunk.page_content for chunk in reranked_chunks)
        answer = generate_answer(context, question)
        metrics["llm_generate_s"] = round(time.monotonic() - t0, 4)

        # ------------------------------------------------------------------
        # Finalise
        # ------------------------------------------------------------------
        metrics["total_s"] = round(time.monotonic() - t_total, 4)
        _write_timing_log(question, metrics, status="ok")
        _print_timing_table(metrics)
        return answer, reranked_chunks, metrics

    except Exception as exc:
        metrics["total_s"] = round(time.monotonic() - t_total, 4)
        _write_timing_log(
            question,
            metrics,
            status="error",
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        raise
