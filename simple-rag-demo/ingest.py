"""
ingest.py — Ingestion pipeline (offline stage).

Stage: Ingestion (run once before querying)
Inputs: PDF files in the documents/ directory
Outputs: FAISS index files saved to the vectorstore/ directory

Pipeline steps:
    1. Load all PDF files from documents/ using PyPDFLoader.
    2. Split extracted text into overlapping chunks using RecursiveCharacterTextSplitter.
    3. Generate vector embeddings for each chunk using HuggingFaceEmbeddings.
    4. Build a FAISS index from the embeddings.
    5. Persist the FAISS index to vectorstore/ for use by rag.py.

Run this module directly to execute the full ingestion pipeline:
    python ingest.py
"""

import glob
import logging
import sys
from pathlib import Path
from typing import List

from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document

from config import (
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    DOCUMENTS_DIR,
    EMBEDDING_MODEL,
    VECTORSTORE_DIR,
    validate_config,
)

logger = logging.getLogger(__name__)


def load_pdf_documents(documents_dir: str) -> List[Document]:
    """
    Recursively finds and loads all PDF files in the given directory.

    Uses PyPDFLoader to extract text from each PDF. If a PDF cannot be read,
    the error is logged and that file is skipped — processing continues for
    all remaining files.

    Args:
        documents_dir: Path to the directory containing PDF files. Subdirectories
                       are searched recursively.

    Returns:
        A combined list of Document objects extracted from all successfully
        loaded PDFs. Each Document contains a page_content string and metadata
        including the source file path.

    Raises:
        SystemExit: If documents_dir does not exist or contains no PDF files.
    """
    documents_path = Path(documents_dir)

    if not documents_path.exists():
        print(
            f"Error: documents/ directory not found or contains no PDF files. "
            f"Expected directory: '{documents_dir}'"
        )
        sys.exit(1)

    pdf_file_paths = glob.glob(str(documents_path / "**" / "*.pdf"), recursive=True)

    if not pdf_file_paths:
        print(
            f"Error: documents/ directory not found or contains no PDF files. "
            f"No *.pdf files found under '{documents_dir}'."
        )
        sys.exit(1)

    all_documents: List[Document] = []

    for pdf_path in pdf_file_paths:
        try:
            loaded_pages = PyPDFLoader(pdf_path).load()
            all_documents.extend(loaded_pages)
        except Exception as load_error:
            logger.error("Failed to load %s: %s. Skipping.", pdf_path, load_error)

    return all_documents


def split_into_chunks(documents: List[Document]) -> List[Document]:
    """
    Splits a list of Documents into smaller, overlapping text chunks.

    Uses RecursiveCharacterTextSplitter configured with CHUNK_SIZE and
    CHUNK_OVERLAP from config.py. Overlapping chunks help preserve context
    at chunk boundaries during retrieval.

    Args:
        documents: List of Document objects to split. Each Document's
                   page_content is split; metadata is preserved on each chunk.

    Returns:
        A list of Document objects where each item represents one chunk.
        The number of returned chunks will be greater than or equal to the
        number of input documents.
    """
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )
    document_chunks = text_splitter.split_documents(documents)
    return document_chunks


def build_vector_store(chunks: List[Document]) -> FAISS:
    """
    Generates embeddings for all chunks and builds an in-memory FAISS index.

    Instantiates HuggingFaceEmbeddings with the model specified in config.py,
    then passes all chunks to FAISS.from_documents to produce a searchable index.

    Args:
        chunks: List of Document objects to embed and index. Each Document's
                page_content is used as the text to embed.

    Returns:
        A FAISS vector store instance containing all chunk embeddings, ready
        for similarity search.
    """
    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    vector_store = FAISS.from_documents(chunks, embeddings)
    return vector_store


def save_vector_store(vector_store: FAISS, vectorstore_dir: str) -> None:
    """
    Persists the FAISS index to disk so it can be loaded by rag.py.

    Saves index files to vectorstore_dir using FAISS.save_local. If the
    directory does not exist it is created automatically by save_local.
    Any existing index in that directory is overwritten.

    Args:
        vector_store: A populated FAISS instance to persist.
        vectorstore_dir: Path to the directory where index files will be written.

    Raises:
        SystemExit: If the index cannot be saved (e.g. permission error,
                    disk full), with a descriptive error message.
    """
    try:
        vector_store.save_local(vectorstore_dir)
    except Exception as save_error:
        print(
            f"Error: Failed to save vector store to vectorstore/: {save_error}."
        )
        sys.exit(1)


def run_ingestion() -> None:
    """
    Orchestrates the full ingestion pipeline from PDFs to a persisted FAISS index.

    Calls load_pdf_documents, split_into_chunks, build_vector_store, and
    save_vector_store in sequence, printing a progress message before each stage
    so the operator can track progress from the terminal.

    Raises:
        SystemExit: Propagated from load_pdf_documents (missing/empty documents
                    directory) or save_vector_store (index persistence failure).
    """
    print("Loading PDFs...")
    loaded_documents = load_pdf_documents(DOCUMENTS_DIR)
    print(f"  Loaded {len(loaded_documents)} page(s) from {DOCUMENTS_DIR}/")

    print("Splitting into chunks...")
    document_chunks = split_into_chunks(loaded_documents)
    print(f"  Produced {len(document_chunks)} chunk(s)")

    print("Building vector store...")
    vector_store = build_vector_store(document_chunks)

    print(f"Saving vector store to {VECTORSTORE_DIR}/...")
    save_vector_store(vector_store, VECTORSTORE_DIR)

    print("Ingestion complete.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    validate_config()
    run_ingestion()
