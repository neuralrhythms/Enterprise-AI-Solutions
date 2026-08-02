"""
rag.py — Online retrieval and answer generation pipeline for simple-rag-demo-v3.

Implements the full query-time RAG pipeline:

1. Index loading: reads FAISS index, BM25 index, and chunk list from disk.
2. Query embedding: prepends BGE query prefix and encodes with BGE model.
3. Candidate retrieval: FAISS + BM25 hybrid search with RRF fusion,
   score threshold filtering, and MMR deduplication.
4. Re-ranking: cross-encoder scoring and top-K selection with parent
   content substitution.
5. Answer generation: Ollama LLM invocation with a structured prompt.

Each pipeline stage is wrapped in a named Langfuse span when tracing is
enabled (LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are set). When keys
are absent the pipeline runs identically with no tracing overhead.

Primary entry point: answer_question(question: str) -> tuple[str, list]
"""

import logging
import pickle
from dataclasses import dataclass, field

import numpy as np
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder

from config import (
    BGE_QUERY_PREFIX,
    CANDIDATE_K,
    EMBEDDING_MODEL,
    GROQ_API_KEY,
    GROQ_MODEL,
    LANGFUSE_HOST,
    LANGFUSE_PUBLIC_KEY,
    LANGFUSE_SECRET_KEY,
    MIN_SCORE,
    TOP_K,
    VECTORSTORE_DIR,
)
from prompts import RAG_PROMPT_TEMPLATE

from langfuse import Langfuse

logger = logging.getLogger(__name__)


def _get_langfuse_client() -> "Langfuse | None":
    """
    Initialise and return a Langfuse client if credentials are configured.

    Returns None when LANGFUSE_PUBLIC_KEY or LANGFUSE_SECRET_KEY is empty,
    allowing the pipeline to run without tracing when Langfuse is not
    configured. No network calls are made when None is returned.

    Returns:
        A configured Langfuse instance, or None if keys are not set.
    """
    if not LANGFUSE_PUBLIC_KEY or not LANGFUSE_SECRET_KEY:
        return None
    return Langfuse(
        public_key=LANGFUSE_PUBLIC_KEY,
        secret_key=LANGFUSE_SECRET_KEY,
        host=LANGFUSE_HOST,
    )


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
    from pathlib import Path

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

def generate_answer(context: str, question: str) -> tuple[str, dict]:
    """
    Generate an answer using Groq cloud inference via the ChatGroq client.

    Groq is the only LLM provider in this version — no local Ollama required.
    Token usage is extracted from the Groq response metadata and returned
    alongside the answer for display in the UI and Langfuse generation tracking.

    Args:
        context:  The concatenated parent chunk text to use as context.
        question: The raw user question string.

    Returns:
        A two-tuple:
        - answer (str): The answer string produced by the LLM.
        - usage (dict): Token usage with keys prompt_tokens, completion_tokens,
          total_tokens extracted from the Groq response metadata.

    Raises:
        ConnectionError: If Groq cannot be reached or the API key is invalid.
    """
    from langchain_groq import ChatGroq

    prompt = RAG_PROMPT_TEMPLATE.format(context=context, question=question)

    try:
        llm = ChatGroq(model=GROQ_MODEL, api_key=GROQ_API_KEY)
        response = llm.invoke(prompt)
        answer = response.content

        # Extract token usage from Groq response metadata.
        usage: dict = {}
        if hasattr(response, "response_metadata"):
            token_info = response.response_metadata.get("token_usage", {})
            usage = {
                "prompt_tokens": token_info.get("prompt_tokens", 0),
                "completion_tokens": token_info.get("completion_tokens", 0),
                "total_tokens": token_info.get("total_tokens", 0),
            }

        return answer, usage

    except Exception as exc:
        error_str = str(exc).lower()
        if any(kw in error_str for kw in ("connection", "api", "authenticate", "401", "403")):
            raise ConnectionError(
                f"Groq is unavailable or returned an error: {exc}. "
                "Check your GROQ_API_KEY and network connection."
            ) from exc
        raise


# ---------------------------------------------------------------------------
# Primary entry point
# ---------------------------------------------------------------------------

def answer_question(question: str) -> tuple[str, list[Document], str | None, dict]:
    """
    Run the full RAG pipeline for a user question and return the answer,
    source chunks, Langfuse trace ID, and token usage.

    Each pipeline stage is wrapped in a named Langfuse span when tracing
    is enabled (LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are set).
    When keys are absent, the pipeline runs identically with no tracing
    overhead.

    Langfuse deployment:
        Self-hosted (local Docker): set LANGFUSE_HOST=http://localhost:3000
        Cloud: set LANGFUSE_HOST=https://cloud.langfuse.com

    Args:
        question: The raw user question string.

    Returns:
        A four-tuple:
        - answer (str): The LLM-generated answer.
        - reranked_chunks (list[Document]): TOP_K documents with parent content
          and rerank_score metadata, used by the UI to render sidebar cards.
        - trace_id (str | None): Langfuse trace ID for this query, used by the
          UI to submit user feedback scores. None when tracing is not configured.
        - usage (dict): Token usage dict with keys prompt_tokens,
          completion_tokens, total_tokens. Empty dict when using Ollama.

    Raises:
        ValueError:        If question is empty or whitespace-only.
        FileNotFoundError: If the vector store has not been built yet.
        RuntimeError:      If no candidates pass the MIN_SCORE filter, or if a
                           required model is not found in the local cache.
        ConnectionError:   If the LLM is unreachable or returns an error.
    """
    if not question or not question.strip():
        raise ValueError("Please enter a question before submitting.")

    langfuse = _get_langfuse_client()
    trace = langfuse.trace(
        name="rag_query",
        input={"question": question},
        metadata={"version": "simple-rag-demo-v3"},
    ) if langfuse else None
    trace_id: str | None = trace.id if trace else None

    def start_span(name: str):
        """Start a Langfuse span if tracing is enabled, else return None."""
        return trace.span(name=name) if trace else None

    def end_span(span, output: dict) -> None:
        """End a Langfuse span with output metadata if it exists."""
        if span:
            span.end(output=output)

    def end_span_error(span, exc: Exception) -> None:
        """End a Langfuse span with error status if it exists."""
        if span:
            span.end(level="ERROR", status_message=str(exc))

    try:
        # usage is initialised here so it is always defined at return time,
        # even if Stage 9 is not reached due to an earlier exception.
        usage: dict = {}

        # ------------------------------------------------------------------
        # Stage 1: Index loading
        # ------------------------------------------------------------------
        span = start_span("index_load")
        try:
            faiss_index, bm25_index, chunks = load_index()
            end_span(span, {"chunks_in_corpus": len(chunks)})
        except Exception as exc:
            end_span_error(span, exc)
            raise

        # ------------------------------------------------------------------
        # Stage 2: BGE model load
        # ------------------------------------------------------------------
        span = start_span("bge_model_load")
        try:
            embeddings = HuggingFaceEmbeddings(
                model_name=EMBEDDING_MODEL,
                model_kwargs={"device": "cpu"},
            )
            end_span(span, {"model": EMBEDDING_MODEL})
        except Exception as exc:
            end_span_error(span, exc)
            raise

        # ------------------------------------------------------------------
        # Stage 3: Query embedding
        # ------------------------------------------------------------------
        span = start_span("query_embed")
        try:
            prefixed_question = BGE_QUERY_PREFIX + question
            query_embedding = np.array(
                embeddings.embed_query(prefixed_question), dtype=np.float32
            )
            end_span(span, {"embedding_dim": len(query_embedding)})
        except Exception as exc:
            end_span_error(span, exc)
            raise

        # ------------------------------------------------------------------
        # Stage 4: FAISS search
        # ------------------------------------------------------------------
        span = start_span("faiss_search")
        try:
            faiss_results: list[tuple[Document, float]] = (
                faiss_index.similarity_search_with_relevance_scores(
                    question, k=CANDIDATE_K
                )
            )
            end_span(span, {"results_returned": len(faiss_results)})
        except Exception as exc:
            end_span_error(span, exc)
            raise

        # ------------------------------------------------------------------
        # Stage 5: BM25 scoring
        # ------------------------------------------------------------------
        span = start_span("bm25_score")
        try:
            tokenised_query = question.split()
            bm25_scores: np.ndarray = bm25_index.get_scores(tokenised_query)
            top_bm25_indices = np.argsort(bm25_scores)[::-1][:CANDIDATE_K]
            end_span(span, {"top_k": CANDIDATE_K})
        except Exception as exc:
            end_span_error(span, exc)
            raise

        # ------------------------------------------------------------------
        # Stage 6: RRF fusion + score filter + MMR
        # ------------------------------------------------------------------
        span = start_span("rrf_mmr")
        try:
            candidates = retrieve_candidates(
                faiss_index, bm25_index, chunks, query_embedding, question,
                faiss_results=faiss_results,
                top_bm25_indices=top_bm25_indices,
            )
            end_span(span, {"candidates_selected": len(candidates)})
        except Exception as exc:
            end_span_error(span, exc)
            raise

        # ------------------------------------------------------------------
        # Stage 7: Cross-encoder model load
        # ------------------------------------------------------------------
        span = start_span("cross_encoder_load")
        try:
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
            end_span(span, {"model": cross_encoder_model_name})
        except Exception as exc:
            end_span_error(span, exc)
            raise

        # ------------------------------------------------------------------
        # Stage 8: Cross-encoder re-ranking
        # ------------------------------------------------------------------
        span = start_span("cross_encoder_rank")
        try:
            reranked_chunks = rerank(candidates, question, cross_encoder)
            end_span(span, {"chunks_returned": len(reranked_chunks)})
        except Exception as exc:
            end_span_error(span, exc)
            raise

        # ------------------------------------------------------------------
        # Stage 9: LLM generation — use Langfuse Generation object so that
        # generation latency, token counts, and cost are tracked separately
        # from plain spans in the Langfuse UI.
        # ------------------------------------------------------------------
        generation = trace.generation(
            name="llm_generate",
            model=GROQ_MODEL,
            input=question,
        ) if trace else None
        try:
            context = "\n\n".join(chunk.page_content for chunk in reranked_chunks)
            answer, usage = generate_answer(context, question)
            if generation:
                generation.end(
                    output=answer,
                    usage={
                        "input": usage.get("prompt_tokens", 0),
                        "output": usage.get("completion_tokens", 0),
                        "total": usage.get("total_tokens", 0),
                    },
                )
        except Exception as exc:
            if generation:
                generation.end(level="ERROR", status_message=str(exc))
            raise

        # ------------------------------------------------------------------
        # Finalise trace — store trace id for user feedback scoring in UI
        # ------------------------------------------------------------------
        trace_id = trace.id if trace else None
        if trace:
            trace.update(output={"answer": answer})
        if langfuse:
            try:
                langfuse.flush()
            except Exception as flush_exc:
                logger.warning("Langfuse flush failed: %s", flush_exc)

        return answer, reranked_chunks, trace_id, usage

    except Exception as exc:
        if trace:
            try:
                trace.update(
                    level="ERROR",
                    status_message=str(exc),
                )
            except Exception:
                pass
        if langfuse:
            try:
                langfuse.flush()
            except Exception:
                pass
        raise
