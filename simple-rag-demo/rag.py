"""
rag.py — Question answering pipeline (online stage).

This module implements the online half of the RAG pipeline. Given a user
question, it loads the persisted FAISS index from disk, retrieves the most
relevant document chunks via similarity search, builds a prompt from those
chunks, and calls the locally-hosted Ollama LLM to generate an answer.

Inputs:
    - question: a non-empty string supplied by the caller (via app.py)
    - persisted FAISS index in vectorstore/ (written by ingest.py)

Outputs:
    - answer: a natural-language string returned by the LLM
    - retrieved_chunks: the List[Document] used as context for that answer

Pipeline stage:
    1. Load FAISS index from disk
    2. Embed question → similarity search → top-K chunks
    3. Format prompt with retrieved context and question
    4. Send prompt to OllamaLLM → return answer text
"""

import requests.exceptions
from pathlib import Path
from typing import List, Tuple

from langchain.schema import Document
from langchain_community.vectorstores import FAISS
from langchain_community.llms import Ollama as OllamaLLM
from langchain_huggingface import HuggingFaceEmbeddings

from prompts import RAG_PROMPT_TEMPLATE
from config import VECTORSTORE_DIR, EMBEDDING_MODEL, OLLAMA_MODEL, TOP_K


def load_vector_store() -> FAISS:
    """
    Loads the persisted FAISS index from VECTORSTORE_DIR.

    Verifies that the vectorstore directory exists and contains a FAISS index
    file before attempting to load it. The embeddings model used here must
    match the one used during ingestion, otherwise retrieved results will be
    meaningless.

    Returns:
        FAISS: The loaded FAISS vector store, ready for similarity search.

    Raises:
        FileNotFoundError: If VECTORSTORE_DIR does not exist or does not
                           contain a FAISS index file (index.faiss).
    """
    vectorstore_path = Path(VECTORSTORE_DIR)
    index_file = vectorstore_path / "index.faiss"

    if not vectorstore_path.exists() or not index_file.exists():
        raise FileNotFoundError(
            "Vector store not found. Run ingest.py first."
        )

    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    vector_store = FAISS.load_local(
        VECTORSTORE_DIR,
        embeddings,
        allow_dangerous_deserialization=True,
    )
    return vector_store


def retrieve_chunks(vector_store: FAISS, question: str) -> List[Document]:
    """
    Retrieves the TOP_K most similar document chunks for the given question.

    Performs a cosine similarity search against the FAISS index using the
    embedded question vector. If the index contains no documents, raises
    RuntimeError rather than silently returning an empty list, because an
    empty context would produce a meaningless LLM response.

    Args:
        vector_store (FAISS): A loaded FAISS index containing document chunk
                              embeddings.
        question (str): The user's question string.

    Returns:
        List[Document]: The TOP_K most relevant Document chunks, each with
                        page_content and source metadata.

    Raises:
        RuntimeError: If the FAISS index contains zero documents.
    """
    retrieved_chunks = vector_store.similarity_search(question, k=TOP_K)

    if not retrieved_chunks:
        raise RuntimeError(
            "Vector store is empty. Re-run ingest.py with valid PDF files."
        )

    return retrieved_chunks


def generate_answer(prompt: str) -> str:
    """
    Sends the formatted prompt to the Ollama LLM and returns the response.

    Instantiates OllamaLLM with a 60-second timeout and calls invoke().
    Connection failures and timeouts are caught broadly and re-raised as
    ConnectionError with a consistent, user-readable message so that app.py
    can display it without exposing raw exception details.

    Args:
        prompt (str): The fully formatted prompt string, including retrieved
                      context and the user's question.

    Returns:
        str: The LLM's generated answer text.

    Raises:
        ConnectionError: If the Ollama service is unreachable, refuses the
                         connection, or does not respond within 60 seconds.
    """
    llm = OllamaLLM(model=OLLAMA_MODEL, timeout=60)

    try:
        response = llm.invoke(prompt)
    except requests.exceptions.ConnectionError:
        raise ConnectionError(
            "Ollama is unavailable. Ensure it is running at localhost:11434."
        )
    except Exception as exc:
        error_message = str(exc).lower()
        if "connection" in error_message or "refused" in error_message or "timeout" in error_message:
            raise ConnectionError(
                "Ollama is unavailable. Ensure it is running at localhost:11434."
            )
        raise

    return response


def answer_question(question: str) -> tuple[str, List[Document]]:
    """
    Orchestrates the full question-answering pipeline for a single question.

    Validates the question, loads the FAISS index, retrieves the most relevant
    document chunks, builds a prompt, calls the LLM, and returns the answer
    alongside the retrieved chunks (so the caller can display source context).

    Args:
        question (str): The user's question. Must be a non-empty, non-whitespace
                        string.

    Returns:
        tuple[str, List[Document]]: A two-element tuple where the first element
            is the LLM-generated answer string and the second is the list of
            Document chunks used as context.

    Raises:
        ValueError: If question is empty or contains only whitespace.
        FileNotFoundError: If the FAISS index does not exist in VECTORSTORE_DIR.
                           Indicates that ingest.py has not been run yet.
        RuntimeError: If the FAISS index exists but contains zero documents.
                      Indicates that ingestion produced an empty index.
        ConnectionError: If the Ollama service is unreachable or times out
                         after 60 seconds.
    """
    if not question or not question.strip():
        raise ValueError("Please enter a question before submitting.")

    vector_store = load_vector_store()
    retrieved_chunks = retrieve_chunks(vector_store, question)

    context_text = "\n\n".join(
        [chunk.page_content for chunk in retrieved_chunks]
    )
    prompt = RAG_PROMPT_TEMPLATE.format(
        context=context_text,
        question=question,
    )

    answer = generate_answer(prompt)

    return answer, retrieved_chunks
