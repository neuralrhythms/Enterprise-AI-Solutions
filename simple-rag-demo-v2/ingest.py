"""
ingest.py — Offline ingestion pipeline for simple-rag-demo-v2.

Orchestrates the full extract → chunk → embed → index workflow:

1. Extractor (pdfplumber): layout-aware text and table extraction,
   section boundary detection, header/footer stripping.
2. Chunker: hierarchical parent-child chunking with overlap reset at
   section boundaries.
3. Embedder: BGE passage-prefix encoding via HuggingFaceEmbeddings.
4. Index Writer: persists FAISS index, BM25 index, and chunk list to
   the vectorstore directory.

Run directly as a script:
    python ingest.py
    python ingest.py --incremental
"""

import argparse
import logging
import pickle
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pdfplumber
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from rank_bm25 import BM25Okapi

from config import (
    BGE_PASSAGE_PREFIX,
    CHILD_CHUNK_OVERLAP,
    CHILD_CHUNK_SIZE,
    DOCUMENTS_DIR,
    EMBEDDING_MODEL,
    PARENT_CHUNK_SIZE,
    VECTORSTORE_DIR,
    validate_config,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class ExtractedPage:
    """
    Represents all extracted content from a single PDF page.

    Attributes:
        source: Absolute file path of the source PDF as a string.
        page_number: 0-indexed page number within the source PDF.
        blocks: Ordered list of text blocks and Markdown-formatted table
                strings extracted from the page.  Each table is inserted
                as a single discrete block at its natural position.
        section_boundaries: Character offsets within the concatenated text
                            of this page at which a new section begins
                            (i.e. where a heading with font_size >
                            body_font_size + 2.0 was detected).
        body_font_size: Median font size across all character objects on
                        the page; used as the baseline for section-boundary
                        detection.
    """

    source: str
    page_number: int
    blocks: list[str] = field(default_factory=list)
    section_boundaries: list[int] = field(default_factory=list)
    body_font_size: float = 0.0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _format_table_as_markdown(table: list[list[Optional[str]]]) -> str:
    """
    Convert a pdfplumber table (list of row lists) into a Markdown table string.

    The first row is treated as the header row.  Empty or None cells are
    rendered as empty strings so the pipe structure is always preserved.

    Args:
        table: A list of rows, where each row is a list of cell strings (or
               None for empty cells).

    Returns:
        A Markdown-formatted table string with pipe-delimited columns,
        e.g.::

            | Header A | Header B |
            | --- | --- |
            | cell 1   | cell 2   |

        Returns an empty string if the table has no rows.
    """
    if not table:
        return ""

    def clean_cell(cell: Optional[str]) -> str:
        # Replace None and strip internal newlines so cells stay on one line.
        if cell is None:
            return ""
        return cell.replace("\n", " ").strip()

    rows = [[clean_cell(cell) for cell in row] for row in table]

    # Header row
    header = "| " + " | ".join(rows[0]) + " |"
    # Separator row
    separator = "| " + " | ".join(["---"] * len(rows[0])) + " |"
    # Data rows
    data_rows = ["| " + " | ".join(row) + " |" for row in rows[1:]]

    parts = [header, separator] + data_rows
    return "\n".join(parts)


def _detect_header_footer_strings(pages_text: list[str], window: int = 3) -> set[str]:
    """
    Identify strings that appear verbatim on 3 or more consecutive pages at the
    same relative position (top or bottom of page text).

    The heuristic checks the first ``window`` non-empty lines and last
    ``window`` non-empty lines of each page.  A candidate string is added to
    the strip set when it appears at the same position across at least 3
    consecutive pages.

    Args:
        pages_text: A list of raw page text strings in page order.
        window: Number of lines to examine at the top and bottom of each page.

    Returns:
        A set of strings that should be stripped from every page's content.
    """
    if len(pages_text) < 3:
        return set()

    def get_edge_lines(text: str) -> tuple[list[str], list[str]]:
        """Return the first and last ``window`` non-empty lines of *text*."""
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        top = lines[:window]
        bottom = lines[-window:] if len(lines) >= window else lines
        return top, bottom

    # Build per-page edge lists
    page_edges: list[tuple[list[str], list[str]]] = [
        get_edge_lines(text) for text in pages_text
    ]

    strip_candidates: set[str] = set()

    num_pages = len(pages_text)

    # Slide a window of 3 consecutive pages and collect matching edge lines
    for i in range(num_pages - 2):
        top_a, bot_a = page_edges[i]
        top_b, bot_b = page_edges[i + 1]
        top_c, bot_c = page_edges[i + 2]

        # Check each position in the top window
        for pos in range(min(len(top_a), len(top_b), len(top_c))):
            line_a = top_a[pos]
            if line_a and line_a == top_b[pos] == top_c[pos]:
                strip_candidates.add(line_a)

        # Check each position in the bottom window
        for pos in range(min(len(bot_a), len(bot_b), len(bot_c))):
            line_a = bot_a[pos]
            if line_a and line_a == bot_b[pos] == bot_c[pos]:
                strip_candidates.add(line_a)

    return strip_candidates


def _strip_header_footer(text: str, strip_set: set[str]) -> str:
    """
    Remove all occurrences of strings in *strip_set* from *text*.

    Each string is removed by filtering out lines that exactly match any
    entry in *strip_set*.  This preserves indentation-sensitive content on
    lines that only partially match.

    Args:
        text: The raw page text to clean.
        strip_set: The set of exact-match strings to remove.

    Returns:
        The cleaned text with matching lines removed and excess blank lines
        collapsed.
    """
    if not strip_set:
        return text

    cleaned_lines: list[str] = []
    for line in text.splitlines():
        stripped_line = line.strip()
        if stripped_line not in strip_set:
            cleaned_lines.append(line)

    return "\n".join(cleaned_lines)


# ---------------------------------------------------------------------------
# Core extraction functions
# ---------------------------------------------------------------------------


def extract_pdf(path: Path) -> list[ExtractedPage]:
    """
    Extract all pages from a single PDF file using pdfplumber.

    For each page the function:

    1. Extracts layout-aware text using ``page.extract_text(x_tolerance=3,
       layout=True)`` to preserve reading order.
    2. Detects tables via ``page.find_tables()`` and inserts each table as a
       discrete Markdown-formatted block at its natural position in the
       content.
    3. Computes the median font size across all character objects on the page
       (``body_font_size``) and records a section boundary (character offset
       within the concatenated page text) for every contiguous span whose
       font size exceeds ``body_font_size + 2.0``.
    4. Strips repeated header/footer/page-number strings — strings appearing
       verbatim on 3 or more consecutive pages at the same relative position
       (top or bottom) — from each page's text content.

    On any exception raised by pdfplumber for a given file, an error is
    logged and an empty list is returned so that the caller can skip the
    file and continue with others.

    Args:
        path: ``pathlib.Path`` pointing to the PDF file to extract.

    Returns:
        A list of :class:`ExtractedPage` objects, one per page, ordered by
        page number.  Returns an empty list if the file cannot be opened or
        parsed.
    """
    try:
        with pdfplumber.open(path) as pdf:
            absolute_source = str(path.resolve())

            # ------------------------------------------------------------------
            # Pass 1: collect raw page text for header/footer detection
            # ------------------------------------------------------------------
            raw_page_texts: list[str] = []
            for page in pdf.pages:
                text = page.extract_text(x_tolerance=3, layout=True) or ""
                raw_page_texts.append(text)

            strip_set = _detect_header_footer_strings(raw_page_texts)

            # ------------------------------------------------------------------
            # Pass 2: build ExtractedPage objects
            # ------------------------------------------------------------------
            extracted_pages: list[ExtractedPage] = []

            for page_index, page in enumerate(pdf.pages):
                raw_text = raw_page_texts[page_index]

                # ----------------------------------------------------------------
                # Compute body_font_size from character objects
                # ----------------------------------------------------------------
                chars = page.chars  # list of dicts with 'size', 'text', 'x0', 'top', etc.
                font_sizes = [
                    char["size"]
                    for char in chars
                    if char.get("size") and char.get("text", "").strip()
                ]

                if font_sizes:
                    body_font_size = statistics.median(font_sizes)
                else:
                    body_font_size = 0.0

                # ----------------------------------------------------------------
                # Identify table bounding boxes so we can splice tables in as
                # discrete blocks instead of the raw extracted text for those
                # regions.
                # ----------------------------------------------------------------
                tables = page.find_tables()

                # Build a sorted list of (top, bottom, markdown_string) for each table
                table_regions: list[tuple[float, float, str]] = []
                for table_obj in tables:
                    extracted = table_obj.extract()
                    if extracted:
                        markdown = _format_table_as_markdown(extracted)
                        if markdown:
                            bbox = table_obj.bbox  # (x0, top, x1, bottom)
                            table_regions.append((bbox[1], bbox[3], markdown))

                # Sort by vertical position (top coordinate)
                table_regions.sort(key=lambda t: t[0])

                # ----------------------------------------------------------------
                # Build blocks by interleaving text regions and table blocks.
                # We crop the page to the areas outside table bounding boxes for
                # text, then insert table markdown at the appropriate position.
                # ----------------------------------------------------------------
                blocks: list[str] = []

                if not table_regions:
                    # No tables — just clean and use the full page text
                    cleaned_text = _strip_header_footer(raw_text, strip_set)
                    if cleaned_text.strip():
                        blocks.append(cleaned_text)
                else:
                    # Crop text from regions between (and after) tables
                    page_height = page.height
                    prev_bottom = 0.0

                    for table_top, table_bottom, md_table in table_regions:
                        # Text region above this table
                        if table_top > prev_bottom:
                            above_crop = page.crop(
                                (0, prev_bottom, page.width, table_top)
                            )
                            above_text = above_crop.extract_text(
                                x_tolerance=3, layout=True
                            ) or ""
                            above_text = _strip_header_footer(above_text, strip_set)
                            if above_text.strip():
                                blocks.append(above_text)

                        # Table block
                        blocks.append(md_table)
                        prev_bottom = table_bottom

                    # Text region below the last table
                    if prev_bottom < page_height:
                        below_crop = page.crop(
                            (0, prev_bottom, page.width, page_height)
                        )
                        below_text = below_crop.extract_text(
                            x_tolerance=3, layout=True
                        ) or ""
                        below_text = _strip_header_footer(below_text, strip_set)
                        if below_text.strip():
                            blocks.append(below_text)

                # ----------------------------------------------------------------
                # Detect section boundaries within the concatenated page text.
                #
                # We work on the cleaned text (excluding table blocks) because
                # font-size data comes from page.chars which corresponds to that
                # text.  We record the character offset in the concatenated
                # blocks text for any span whose size > body_font_size + 2.0.
                # ----------------------------------------------------------------
                section_boundaries: list[int] = []

                if body_font_size > 0.0 and chars:
                    heading_threshold = body_font_size + 2.0

                    # Concatenate all blocks to compute offsets within that string
                    concatenated = "\n".join(blocks)

                    # Group consecutive chars that share the same "is heading" status
                    # and detect transitions from body → heading.
                    # We use a simple scan: when we see a char with size > threshold
                    # that is preceded by a char with size <= threshold (or is the
                    # first char), we record a boundary.
                    #
                    # To map char objects back to offsets in `concatenated`, we
                    # re-extract text without layout to get a clean char sequence,
                    # then walk the concatenated text to find matching positions.
                    # This is an approximation: we record the offset of the first
                    # character in the concatenated text where a heading span begins.

                    in_heading_span = False
                    current_offset = 0  # tracks position in concatenated string

                    for char in chars:
                        char_text = char.get("text", "")
                        if not char_text:
                            continue

                        char_size = char.get("size", 0.0)
                        is_heading_char = char_size > heading_threshold

                        if is_heading_char and not in_heading_span:
                            # Find where this character appears in the concatenated text
                            # starting from current_offset.
                            pos = concatenated.find(char_text, current_offset)
                            if pos != -1 and pos not in section_boundaries:
                                section_boundaries.append(pos)
                            in_heading_span = True
                        elif not is_heading_char:
                            in_heading_span = False

                extracted_pages.append(
                    ExtractedPage(
                        source=absolute_source,
                        page_number=page_index,
                        blocks=blocks,
                        section_boundaries=sorted(set(section_boundaries)),
                        body_font_size=body_font_size,
                    )
                )

            return extracted_pages

    except Exception as e:
        logger.error(f"Failed to extract {path}: {e}")
        return []


def extract_documents(documents_dir: str) -> list[ExtractedPage]:
    """
    Walk a directory recursively and extract all PDF files found within it.

    Calls :func:`extract_pdf` on every ``*.pdf`` file discovered.  Results
    from all files are concatenated in the order the files are found.

    Args:
        documents_dir: Path to the directory containing PDF files.  The
                       directory is searched recursively.

    Returns:
        A flat list of :class:`ExtractedPage` objects from all successfully
        parsed PDF files.

    Raises:
        FileNotFoundError: If ``documents_dir`` does not exist.
    """
    dir_path = Path(documents_dir)

    if not dir_path.exists():
        raise FileNotFoundError(
            f"Documents directory not found: {documents_dir}"
        )

    pdf_files = sorted(dir_path.rglob("*.pdf"))

    if not pdf_files:
        logger.warning(
            f"No PDF files found in documents directory: {documents_dir}"
        )
        return []

    all_pages: list[ExtractedPage] = []
    for pdf_path in pdf_files:
        pages = extract_pdf(pdf_path)
        all_pages.extend(pages)

    return all_pages


# ---------------------------------------------------------------------------
# Chunker
# ---------------------------------------------------------------------------


def chunk_document(pages: list[ExtractedPage]) -> list[Document]:
    """
    Convert a list of ExtractedPage objects into a flat list of child Document
    objects using hierarchical parent-child chunking.

    The function operates in two passes:

    **Pass 1 — Parent chunking**

    Walks all pages' blocks sequentially.  For each block a sorted list of
    split points is assembled from two sources:

    - Section boundaries (translated from page-level character offsets into
      block-local offsets).  These are *preferred* split points; the current
      parent is always flushed before the segment that begins at a boundary.
    - Paragraph breaks (``"\\n\\n"``), used as fallback splits when no
      boundary is near.

    The block is split at every split point, and each resulting segment is
    appended to the current parent buffer.  Whenever a segment starts at a
    section boundary the existing buffer (if non-empty) is flushed first,
    then the new parent begins with that segment.  The parent is also flushed
    unconditionally when the accumulated character count would exceed
    ``PARENT_CHUNK_SIZE`` after adding a new segment.

    Each parent is represented as a plain dict carrying:

    - ``text``             — the accumulated (stripped) text for this parent
    - ``source``           — source file path (from the first page that
                            contributed text to this parent)
    - ``page_number``      — page number of the first contributing page
    - ``section_heading``  — first non-empty line of the segment that started
                            the parent at a section boundary (``None`` if the
                            parent was started for another reason)
    - ``boundaries``       — section boundary offsets relative to ``text``
                            (used in Pass 2 for overlap-reset logic)

    **Pass 2 — Child chunking**

    For each parent dict, a sliding window of ``CHILD_CHUNK_SIZE`` characters
    is advanced by ``CHILD_CHUNK_SIZE - CHILD_CHUNK_OVERLAP`` characters per
    step.  Before each advance the function checks whether any section
    boundary recorded for the parent falls inside the overlap window (i.e.
    between ``default_next_start`` and ``window_end``).  When such a boundary
    exists the next child starts exactly at the earliest such boundary rather
    than at the overlap-adjusted position, so the overlap never spans a
    section boundary.

    Each child is a LangChain ``Document`` with:

    - ``page_content``     — child text (≤ ``CHILD_CHUNK_SIZE`` chars)
    - ``metadata``         — dict with keys ``source``, ``page_number``,
                            ``section_heading`` (``str`` or ``None``),
                            ``parent_content`` (full parent text), and
                            ``rerank_score`` (initialised to ``0.0``).

    Only child ``Document`` objects are returned; parent text is stored
    exclusively in ``child.metadata["parent_content"]``.

    Args:
        pages: Ordered list of :class:`ExtractedPage` objects, typically the
               output of :func:`extract_documents`.

    Returns:
        A flat list of LangChain ``Document`` objects representing all child
        chunks across all input pages.  Returns an empty list if ``pages``
        is empty or all pages have empty blocks.
    """
    # ------------------------------------------------------------------
    # Pass 1: Build parent chunks
    # ------------------------------------------------------------------
    parent_chunks: list[dict] = []

    # Mutable accumulator state for the parent currently being built.
    buf_text: str = ""
    buf_source: str = ""
    buf_page_number: int = 0
    buf_section_heading: Optional[str] = None
    # Section boundary offsets within buf_text (used in Pass 2).
    buf_boundaries: list[int] = []

    def flush_parent() -> None:
        """
        Save the current buffer as a completed parent chunk and reset state.

        Does nothing when the buffer contains only whitespace.
        """
        nonlocal buf_text, buf_section_heading, buf_boundaries

        stripped = buf_text.strip()
        if not stripped:
            buf_text = ""
            buf_section_heading = None
            buf_boundaries = []
            return

        # Re-base boundary offsets relative to the stripped text.
        # strip() only removes leading/trailing whitespace, so we subtract
        # the number of leading whitespace characters from each stored offset.
        leading_ws = len(buf_text) - len(buf_text.lstrip())
        rebased_boundaries = sorted(
            b - leading_ws
            for b in buf_boundaries
            if b - leading_ws >= 0
        )

        parent_chunks.append(
            {
                "text": stripped,
                "source": buf_source,
                "page_number": buf_page_number,
                "section_heading": buf_section_heading,
                "boundaries": rebased_boundaries,
            }
        )

        buf_text = ""
        buf_section_heading = None
        buf_boundaries = []

    # Walk every page and every block within each page.
    for page in pages:
        # We need page-level boundary offsets (within the concatenated page
        # text) translated into block-local offsets.  The Extractor stores
        # section_boundaries as offsets within "\n".join(page.blocks).
        #
        # We track `page_offset` — the character position at which the current
        # block begins within that concatenated string.
        page_offset = 0

        for block in page.blocks:
            block_len = len(block)

            # ----------------------------------------------------------------
            # Find section boundaries that fall within this block.
            # A page-level offset `b` maps to block-local offset `b - page_offset`
            # when page_offset <= b < page_offset + block_len.
            # ----------------------------------------------------------------
            block_boundaries: list[int] = sorted(
                b - page_offset
                for b in page.section_boundaries
                if page_offset <= b < page_offset + block_len
            )

            # ----------------------------------------------------------------
            # Build the list of split points for this block.
            # Each entry is (block_local_offset, is_section_boundary).
            # The offset marks the START of a new segment; text before the
            # first split point (offset 0) is the first segment.
            # ----------------------------------------------------------------
            split_points: list[tuple[int, bool]] = []

            for b in block_boundaries:
                if b > 0:  # offset 0 means the block itself starts at a boundary
                    split_points.append((b, True))

            # Paragraph breaks: the next segment starts right after "\n\n".
            pos = 0
            while True:
                found = block.find("\n\n", pos)
                if found == -1:
                    break
                next_seg_start = found + 2  # segment starts after the two newlines
                if next_seg_start < block_len:
                    split_points.append((next_seg_start, False))
                pos = found + 1

            # Sort by offset; section boundaries win over paragraph breaks at
            # the same position.
            split_points.sort(key=lambda sp: (sp[0], not sp[1]))

            # Deduplicate: if two split points share an offset, keep the one
            # that is a section boundary (or the first encountered).
            deduplicated: list[tuple[int, bool]] = []
            for offset, is_boundary in split_points:
                if deduplicated and deduplicated[-1][0] == offset:
                    # Upgrade to boundary-level if either entry is a boundary.
                    prev_offset, prev_is_boundary = deduplicated[-1]
                    deduplicated[-1] = (prev_offset, prev_is_boundary or is_boundary)
                else:
                    deduplicated.append((offset, is_boundary))

            # ----------------------------------------------------------------
            # Determine whether the block itself starts at a section boundary
            # (block_local offset 0 was in the original block_boundaries list).
            # ----------------------------------------------------------------
            block_starts_at_boundary = 0 in block_boundaries
            first_segment_is_boundary = block_starts_at_boundary

            # ----------------------------------------------------------------
            # Walk the split points and emit segments into the parent buffer.
            # ----------------------------------------------------------------
            seg_start = 0

            # Convenience: the split-point list gives the START positions of
            # subsequent segments.  We need to iterate over each segment in
            # order, so we include an implicit sentinel at the end.
            all_segments: list[tuple[int, int, bool]] = []  # (seg_start, seg_end, is_boundary_start)

            all_seg_starts = [0] + [sp[0] for sp in deduplicated]
            all_seg_is_boundary = [first_segment_is_boundary] + [sp[1] for sp in deduplicated]

            for i, start in enumerate(all_seg_starts):
                end = all_seg_starts[i + 1] if i + 1 < len(all_seg_starts) else block_len
                all_segments.append((start, end, all_seg_is_boundary[i]))

            for seg_start_pos, seg_end_pos, seg_is_boundary in all_segments:
                segment = block[seg_start_pos:seg_end_pos]
                if not segment:
                    continue

                # If this segment begins at a section boundary, flush the
                # current buffer first (if it has content), then start the
                # new parent with this segment as its opening content.
                if seg_is_boundary and buf_text.strip():
                    flush_parent()

                # Initialise source/page tracking when the buffer is empty.
                if not buf_text:
                    buf_source = page.source
                    buf_page_number = page.page_number

                    if seg_is_boundary:
                        # Record the first non-empty line as the section heading.
                        first_line = segment.strip().splitlines()[0] if segment.strip() else None
                        buf_section_heading = first_line

                # Size overflow: flush before adding the segment when the
                # combined length would exceed PARENT_CHUNK_SIZE.
                # When the buffer is empty (or the segment alone exceeds the
                # limit), we must still feed the segment without looping; we do
                # so by slicing the segment into PARENT_CHUNK_SIZE pieces and
                # flushing between each piece.
                if buf_text.strip() and (len(buf_text) + len(segment)) > PARENT_CHUNK_SIZE:
                    flush_parent()
                    buf_source = page.source
                    buf_page_number = page.page_number

                # When this segment starts at a section boundary, record the
                # current buffer length as a boundary offset within the parent.
                if seg_is_boundary:
                    boundary_pos = len(buf_text)
                    if boundary_pos not in buf_boundaries:
                        buf_boundaries.append(boundary_pos)

                # Feed the segment in PARENT_CHUNK_SIZE slices so that even
                # segments that are individually larger than PARENT_CHUNK_SIZE
                # are correctly broken into separate parents.
                seg_cursor = 0
                while seg_cursor < len(segment):
                    remaining_capacity = PARENT_CHUNK_SIZE - len(buf_text)
                    slice_end = seg_cursor + remaining_capacity
                    chunk_slice = segment[seg_cursor:slice_end]
                    buf_text += chunk_slice
                    seg_cursor = slice_end

                    if seg_cursor < len(segment):
                        # Buffer is now full; flush and start a new parent.
                        flush_parent()
                        buf_source = page.source
                        buf_page_number = page.page_number

            # Advance page_offset past this block and the joining "\n".
            page_offset += block_len + 1  # +1 for the "\n" in "\n".join(...)

    # Flush any remaining text as the final parent.
    flush_parent()

    # ------------------------------------------------------------------
    # Pass 2: Produce child chunks from each parent
    # ------------------------------------------------------------------
    child_documents: list[Document] = []

    for parent in parent_chunks:
        parent_text: str = parent["text"]
        parent_source: str = parent["source"]
        parent_page_number: int = parent["page_number"]
        parent_section_heading: Optional[str] = parent["section_heading"]
        parent_boundaries: list[int] = parent["boundaries"]

        # Slide a window of CHILD_CHUNK_SIZE chars over the parent text.
        window_start = 0

        while window_start < len(parent_text):
            window_end = min(window_start + CHILD_CHUNK_SIZE, len(parent_text))
            child_text = parent_text[window_start:window_end]

            child_documents.append(
                Document(
                    page_content=child_text,
                    metadata={
                        "source": parent_source,
                        "page_number": parent_page_number,
                        "section_heading": parent_section_heading,
                        "parent_content": parent_text,
                        "rerank_score": 0.0,
                    },
                )
            )

            if window_end >= len(parent_text):
                # Reached the end of the parent text; no more children needed.
                break

            # Default next window start: advance by stride = CHILD_CHUNK_SIZE - CHILD_CHUNK_OVERLAP.
            stride = CHILD_CHUNK_SIZE - CHILD_CHUNK_OVERLAP
            default_next_start = window_start + stride

            # Check whether any section boundary falls inside the overlap
            # window — i.e. in the half-open interval [default_next_start, window_end).
            # If one does, the overlap would cross a section boundary, which is
            # forbidden by Requirement 2.3.  Instead, snap to the earliest such
            # boundary so the next child starts exactly at the section break.
            overlap_boundaries = [
                b for b in parent_boundaries
                if default_next_start <= b < window_end
            ]

            if overlap_boundaries:
                # Snap to the earliest boundary inside the overlap window.
                window_start = min(overlap_boundaries)
            else:
                window_start = default_next_start

    return child_documents


# ---------------------------------------------------------------------------
# Embedder
# ---------------------------------------------------------------------------


def embed_and_index(chunks: list[Document]) -> tuple[FAISS, BM25Okapi]:
    """
    Embed a list of child chunk Documents and build both a FAISS vector index
    and a BM25 keyword index.

    The BGE model requires a passage prefix to be prepended to each chunk's
    text before encoding.  New Document objects are created with the prefixed
    content so that the originals are not mutated; the original (non-prefixed)
    text is used for BM25 tokenisation as BM25 does not benefit from the BGE
    asymmetric prefix.

    Args:
        chunks: List of child chunk ``Document`` objects produced by
                :func:`chunk_document`.

    Returns:
        A tuple ``(faiss_index, bm25_index)`` where:
        - ``faiss_index`` is a :class:`langchain_community.vectorstores.FAISS`
          instance built from the passage-prefixed chunk embeddings.
        - ``bm25_index`` is a :class:`rank_bm25.BM25Okapi` instance built
          from word-tokenised original (non-prefixed) chunk text.

    Raises:
        ValueError: If ``chunks`` is empty.
    """
    if not chunks:
        raise ValueError("Cannot build an index from an empty chunk list.")

    logger.info(f"Embedding {len(chunks)} chunks using model '{EMBEDDING_MODEL}'...")

    # Initialise the BGE embedding model targeting CPU only.
    # device="cpu" is mandatory per the hardware constraints of this project.
    embeddings = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL,
        model_kwargs={"device": "cpu"},
    )

    # Prepend the BGE passage prefix to each chunk before encoding.
    # We create new Document objects to avoid mutating the originals; the
    # original metadata is preserved unchanged.
    prefixed_chunks = [
        Document(
            page_content=BGE_PASSAGE_PREFIX + chunk.page_content,
            metadata=chunk.metadata,
        )
        for chunk in chunks
    ]

    # Build the FAISS index from the prefixed documents.
    faiss_index = FAISS.from_documents(prefixed_chunks, embeddings)

    # Build the BM25 index from word-tokenised original (non-prefixed) text.
    # BM25Okapi is not appendable — it must be fully rebuilt whenever the
    # corpus changes (e.g. during incremental updates).
    tokenised_corpus = [chunk.page_content.split() for chunk in chunks]
    bm25_index = BM25Okapi(tokenised_corpus)

    logger.info("FAISS and BM25 indexes built successfully.")

    return faiss_index, bm25_index


# ---------------------------------------------------------------------------
# Index Writer
# ---------------------------------------------------------------------------


def save_index(
    faiss_index: FAISS,
    bm25_index: BM25Okapi,
    chunks: list[Document],
    vectorstore_dir: str,
) -> None:
    """
    Persist the FAISS index, BM25 index, and child chunk list to disk.

    Creates ``vectorstore_dir`` if it does not already exist.  Three files
    are written:

    - ``index.faiss``  — the FAISS binary index (via LangChain's ``save_local``)
    - ``bm25.pkl``     — the serialised :class:`rank_bm25.BM25Okapi` instance
    - ``chunks.pkl``   — the serialised ``list[Document]`` (child chunks with
                         full metadata) needed by the Retriever at query time

    Args:
        faiss_index: A built :class:`FAISS` vectorstore instance.
        bm25_index: A built :class:`rank_bm25.BM25Okapi` instance.
        chunks: The list of original (non-prefixed) child chunk ``Document``
                objects whose text and metadata should be persisted.
        vectorstore_dir: Path to the directory where artefacts will be saved.
                         The directory is created if it does not exist.
    """
    dir_path = Path(vectorstore_dir)
    dir_path.mkdir(parents=True, exist_ok=True)

    # Save the FAISS index; LangChain writes index.faiss and index.pkl into the
    # target directory automatically.
    faiss_index.save_local(vectorstore_dir)
    logger.info(f"FAISS index saved to '{vectorstore_dir}/index.faiss'.")

    # Pickle the BM25 index.
    bm25_path = dir_path / "bm25.pkl"
    with open(bm25_path, "wb") as bm25_file:
        pickle.dump(bm25_index, bm25_file)
    logger.info(f"BM25 index saved to '{bm25_path}'.")

    # Pickle the chunk list so the Retriever can reconstruct parent context
    # without re-embedding at query time.
    chunks_path = dir_path / "chunks.pkl"
    with open(chunks_path, "wb") as chunks_file:
        pickle.dump(chunks, chunks_file)
    logger.info(f"Chunk list ({len(chunks)} chunks) saved to '{chunks_path}'.")


# ---------------------------------------------------------------------------
# Incremental update
# ---------------------------------------------------------------------------


def incremental_update(new_chunks: list[Document], vectorstore_dir: str) -> None:
    """
    Append new child chunks to an existing vectorstore without discarding
    previously indexed chunks.

    The function loads the existing FAISS index, BM25 index, and chunk list
    from disk, merges them with the new chunks, and writes the updated
    artefacts back.

    **BM25 note:** :class:`rank_bm25.BM25Okapi` is not appendable — it must
    be fully rebuilt from the complete corpus (old + new chunks) every time.
    This is expected behaviour and is reflected in the implementation.

    If no existing index is found (e.g. the vectorstore directory is absent or
    ``index.faiss`` is missing), a warning is logged and a full rebuild is
    triggered via :func:`run_ingestion`.

    Args:
        new_chunks: List of new child chunk ``Document`` objects to add.
        vectorstore_dir: Path to the directory containing the existing index
                         artefacts.
    """
    dir_path = Path(vectorstore_dir)
    faiss_path = dir_path / "index.faiss"
    bm25_path = dir_path / "bm25.pkl"
    chunks_path = dir_path / "chunks.pkl"

    # Guard: if the existing index is absent, fall back to a full rebuild.
    if not (faiss_path.exists() and bm25_path.exists() and chunks_path.exists()):
        logger.warning(
            "Incremental update requested but no existing index found in "
            f"'{vectorstore_dir}'. Falling back to a full rebuild."
        )
        run_ingestion(incremental=False)
        return

    logger.info(f"Loading existing index from '{vectorstore_dir}' for incremental update...")

    # Re-create the embedding model (same config as during initial ingestion).
    embeddings = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL,
        model_kwargs={"device": "cpu"},
    )

    # Load the existing FAISS index.
    faiss_index = FAISS.load_local(
        vectorstore_dir,
        embeddings,
        allow_dangerous_deserialization=True,
    )

    # Load the existing chunk list.
    with open(chunks_path, "rb") as f:
        existing_chunks: list[Document] = pickle.load(f)

    # Embed and append the new chunks to the FAISS index.
    # We prepend the BGE passage prefix to new chunks before adding them,
    # matching the encoding convention used during initial ingestion.
    new_prefixed_chunks = [
        Document(
            page_content=BGE_PASSAGE_PREFIX + chunk.page_content,
            metadata=chunk.metadata,
        )
        for chunk in new_chunks
    ]
    faiss_index.add_documents(new_prefixed_chunks)

    # Merge chunk lists: old chunks first, then new.
    all_chunks = existing_chunks + new_chunks

    # Rebuild BM25 over the full combined corpus.
    # BM25Okapi cannot be appended to; a full rebuild is always required.
    tokenised_corpus = [chunk.page_content.split() for chunk in all_chunks]
    bm25_index = BM25Okapi(tokenised_corpus)

    # Persist the updated artefacts.
    save_index(faiss_index, bm25_index, all_chunks, vectorstore_dir)

    logger.info(
        f"Incremental update complete. Added {len(new_chunks)} new chunks "
        f"(total: {len(all_chunks)})."
    )


# ---------------------------------------------------------------------------
# Ingestion entry point
# ---------------------------------------------------------------------------


def run_ingestion(incremental: bool = False) -> None:
    """
    Execute the full offline ingestion pipeline: extract → chunk → embed → index.

    This is the top-level orchestrator called by the ``__main__`` block and
    by :func:`incremental_update` when no existing index is found.

    Steps:

    1. Extract all PDF pages from ``DOCUMENTS_DIR`` via :func:`extract_documents`.
    2. Produce child chunks via :func:`chunk_document`.
    3. If ``incremental=True`` **and** an existing index is present in
       ``VECTORSTORE_DIR``, delegate to :func:`incremental_update` to append
       only new chunks.
    4. Otherwise perform a full embed-and-index via :func:`embed_and_index`
       followed by :func:`save_index`.

    Args:
        incremental: When ``True``, attempt to append new chunks to the
                     existing index rather than rebuilding from scratch.
                     Falls back to a full rebuild if no existing index is found.
    """
    logger.info("Starting ingestion pipeline...")

    # Step 1: Extract all PDF pages from the documents directory.
    pages = extract_documents(DOCUMENTS_DIR)

    # Step 2: Produce hierarchical child chunks.
    chunks = chunk_document(pages)
    logger.info(f"Chunking complete: {len(chunks)} child chunks produced.")

    if not chunks:
        logger.warning("No chunks produced. Nothing to index.")
        return

    # Step 3: Decide between incremental update and full rebuild.
    dir_path = Path(VECTORSTORE_DIR)
    existing_index_present = (dir_path / "index.faiss").exists()

    if incremental and existing_index_present:
        logger.info("Incremental mode: appending new chunks to existing index.")
        incremental_update(chunks, VECTORSTORE_DIR)
    else:
        # Full rebuild: embed all chunks and write fresh artefacts.
        faiss_index, bm25_index = embed_and_index(chunks)
        save_index(faiss_index, bm25_index, chunks, VECTORSTORE_DIR)

    logger.info("Ingestion pipeline complete.")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Ingest PDFs into the v2 RAG vectorstore.")
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Append new documents to existing index.",
    )
    args = parser.parse_args()
    validate_config()
    run_ingestion(incremental=args.incremental)
