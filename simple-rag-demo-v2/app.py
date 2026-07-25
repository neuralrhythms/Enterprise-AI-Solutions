"""
app.py — Streamlit UI entry point for simple-rag-demo-v2.

Renders the wide-layout dark-themed interface, including the hero header,
question input with live character counter, stage-aware spinners, metric
cards for retrieval and generation time, an answer card with custom CSS,
and a sidebar panel displaying retrieved chunk cards with colour-coded
similarity scores.

Startup sequence (in order):
  1. st.set_page_config — must be the first Streamlit call
  2. inject_custom_css — inject dark-theme CSS overrides
  3. validate_config — halt if any constant is out of range
  4. check_vector_store — halt if index.faiss is missing
  5. check_ollama — halt if Ollama is not reachable
  6. render_hero_header — gradient title + subtitle
  7. render_main_panel — question input, submit logic, answer display

Session state keys:
  "question"       — text_input widget key (reset by clear_pending flag)
  "clear_pending"  — boolean flag: reset question on next rerun
  "last_answer"    — most recent answer string
  "last_chunks"    — most recent list[Document]
  "last_metrics"   — most recent metrics dict with TIMING_KEYS timing values
"""

import urllib.request
from pathlib import Path

import streamlit as st

from config import VECTORSTORE_DIR, validate_config
from rag import answer_question

# ---------------------------------------------------------------------------
# 1. Page config — MUST be the first Streamlit call in the script
# ---------------------------------------------------------------------------
st.set_page_config(
    layout="wide",
    page_title="Intelligent Document Search v2",
    page_icon="🔍",
)


# ---------------------------------------------------------------------------
# CSS injection
# ---------------------------------------------------------------------------

def inject_custom_css() -> None:
    """
    Inject custom CSS into the Streamlit app via st.markdown.

    Styles applied:
    - Rounded corners on text input fields (border-radius: 8px)
    - Answer card: dark background (#1e2a38), left accent border (#3498db),
      rounded corners, comfortable padding
    - Sidebar chunk card: dark background (#1a2332), subtle border,
      rounded corners, smaller font size
    - Source badge: monospace pill badge for filename display
    """
    st.markdown(
        """
        <style>
        /* Rounded input fields */
        div[data-testid="stTextInput"] input {
            border-radius: 8px;
        }
        /* Answer card */
        .answer-card {
            background-color: #1e2a38;
            border-left: 4px solid #3498db;
            border-radius: 6px;
            padding: 16px 20px;
            margin-top: 8px;
        }
        /* Sidebar chunk card */
        .chunk-card {
            background-color: #1a2332;
            border: 1px solid #2c3e50;
            border-radius: 6px;
            padding: 12px;
            margin-bottom: 10px;
            font-size: 0.85em;
        }
        /* Source badge */
        .source-badge {
            background-color: #2c3e50;
            color: #bdc3c7;
            border-radius: 4px;
            padding: 2px 6px;
            font-size: 0.8em;
            font-family: monospace;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Startup guards
# ---------------------------------------------------------------------------

def _validate_config_or_stop() -> None:
    """
    Run validate_config() and halt the app if any constant is out of range.

    Displays a st.error with the ValueError message and calls st.stop()
    so no further rendering occurs.
    """
    try:
        validate_config()
    except ValueError as exc:
        st.error(str(exc))
        st.stop()


def _check_vector_store_or_stop() -> None:
    """
    Verify that the FAISS index file exists on disk.

    Looks for ``VECTORSTORE_DIR/index.faiss``. If the file is absent,
    displays a st.error and calls st.stop() to prevent further rendering.
    """
    index_path = Path(VECTORSTORE_DIR) / "index.faiss"
    if not index_path.exists():
        st.error("Vector store not found. Run ingest.py first.")
        st.stop()


def _check_ollama_or_stop() -> None:
    """
    Verify that the Ollama service is reachable at localhost:11434.

    Makes a lightweight HTTP request with a 2-second timeout. On any
    exception (connection refused, timeout, etc.) displays a st.error
    and calls st.stop().
    """
    try:
        urllib.request.urlopen("http://localhost:11434", timeout=2)
    except Exception:
        st.error(
            "Ollama is unavailable. Ensure it is running at localhost:11434."
        )
        st.stop()


# ---------------------------------------------------------------------------
# Hero header
# ---------------------------------------------------------------------------

def render_hero_header() -> None:
    """
    Render the gradient hero header with title and subtitle.

    Uses inline CSS to produce a WebKit gradient text effect on the title.
    Falls back to a plain visible title for browsers that do not support
    -webkit-background-clip (the gradient simply disappears; the text
    remains readable because Streamlit's dark theme provides contrast).
    """
    st.markdown(
        """
        <div style="text-align: center; padding: 20px 0 10px 0;">
            <h1 style="background: linear-gradient(90deg, #3498db, #9b59b6);
                       -webkit-background-clip: text;
                       -webkit-text-fill-color: transparent;
                       font-size: 2.4em; margin-bottom: 4px;">
                🔍 Intelligent Document Search v2
            </h1>
            <p style="color: #7f8c8d; font-size: 1.05em; margin: 0;">
                Hierarchical RAG · BGE Embeddings · Hybrid Retrieval · Cross-Encoder Re-ranking
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Score colour helper
# ---------------------------------------------------------------------------

def score_color(score: float) -> str:
    """
    Map a re-ranking score to a CSS hex colour string.

    Thresholds:
    - score >= 0.80  →  green  (#2ecc71)
    - 0.50 <= score < 0.80  →  orange (#e67e22)
    - score < 0.50  →  red    (#e74c3c)

    Args:
        score: A float similarity/re-ranking score, typically in [0.0, 1.0].

    Returns:
        A CSS hex colour string (e.g. "#2ecc71").
    """
    if score >= 0.80:
        return "#2ecc71"
    if score >= 0.50:
        return "#e67e22"
    return "#e74c3c"


def _top_two_stages(metrics: dict) -> list[tuple[str, float]]:
    """
    Return the two pipeline stages with the highest non-None timing values,
    excluding total_s.

    Ties are broken by the stage's position in TIMING_KEYS (earlier position
    wins), because Python's sort is stable and we iterate in TIMING_KEYS order.

    Args:
        metrics: The Metrics Dict returned by answer_question(), containing
                 the ten TIMING_KEYS as keys.

    Returns:
        A list of at most two (stage_name, duration) tuples ordered by
        descending duration.
    """
    from rag import TIMING_KEYS

    candidates = [
        (key, metrics[key])
        for key in TIMING_KEYS
        if key != "total_s" and metrics.get(key) is not None
    ]
    # Stable sort descending by duration — preserves TIMING_KEYS insertion
    # order for equal values, so ties always resolve predictably.
    candidates.sort(key=lambda item: item[1], reverse=True)
    return candidates[:2]


# ---------------------------------------------------------------------------
# Sidebar chunk cards
# ---------------------------------------------------------------------------

def render_sidebar_chunks(chunks: list) -> None:
    """
    Render retrieved chunk cards in the Streamlit sidebar.

    Each card displays:
    - A source badge showing the document filename.
    - A colour-coded score indicator using the rerank_score metadata field.
    - An optional section heading (italic, muted).
    - A truncated preview of the chunk content (280 characters).

    Args:
        chunks: A list of LangChain Document objects returned by the RAG
                pipeline. Each document is expected to have metadata keys
                ``source``, ``rerank_score``, and optionally
                ``section_heading``.
    """
    with st.sidebar:
        st.markdown("### 📚 Retrieved Chunks")
        for chunk in chunks:
            score = chunk.metadata.get("rerank_score", 0.0)
            color = score_color(score)
            filename = Path(chunk.metadata.get("source", "unknown")).name
            section = chunk.metadata.get("section_heading") or ""
            preview = (
                chunk.page_content[:280] + "…"
                if len(chunk.page_content) > 280
                else chunk.page_content
            )

            # Build optional section heading HTML only when a heading exists.
            # This avoids rendering an empty <div> that would add whitespace.
            section_html = (
                f"<div style='color: #85929e; font-style: italic; "
                f"margin-bottom: 4px; font-size: 0.8em;'>{section}</div>"
                if section
                else ""
            )

            st.markdown(
                f"""
                <div class="chunk-card">
                    <div style="margin-bottom: 6px;">
                        <span class="source-badge">{filename}</span>
                        <span style="color: {color}; margin-left: 8px; font-weight: bold;">● {score:.2f}</span>
                    </div>
                    {section_html}
                    <div style="color: #bdc3c7;">{preview}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


# ---------------------------------------------------------------------------
# Answer display
# ---------------------------------------------------------------------------

def render_answer(answer: str, metrics: dict) -> None:
    """
    Render the answer card, dynamic top-two timing metric cards, and the
    expandable timing breakdown table.

    The two metric cards show the pipeline stages with the longest measured
    durations (excluding total_s), determined dynamically from the metrics
    dict so the cards always reflect the actual bottleneck.

    The timing breakdown expander shows all ten stages from TIMING_KEYS in
    order, with durations formatted to three decimal places. Stages that did
    not complete (None value) are shown as "—".

    Args:
        answer:  The answer string returned by the RAG pipeline.
        metrics: The Metrics Dict containing the ten TIMING_KEYS timing values.
    """
    from rag import TIMING_KEYS

    # Dynamic top-two metric cards — show the two slowest individual stages.
    top_two = _top_two_stages(metrics)
    if top_two:
        metric_cols = st.columns(len(top_two))
        for col, (stage, duration) in zip(metric_cols, top_two):
            label = stage.replace("_s", "").replace("_", " ").title()
            col.metric(f"⏱ {label}", f"{duration:.1f}s")

    # Answer card with left accent border.
    st.markdown(
        f'<div class="answer-card">{answer}</div>',
        unsafe_allow_html=True,
    )

    # Expandable timing breakdown — all ten stages in TIMING_KEYS order.
    with st.expander("⏱ Timing Breakdown"):
        rows = []
        for key in TIMING_KEYS:
            value = metrics.get(key)
            display = f"{value:.3f}" if value is not None else "—"
            rows.append({"Stage": key, "Time (s)": display})
        st.table(rows)


# ---------------------------------------------------------------------------
# Main panel
# ---------------------------------------------------------------------------

def render_main_panel() -> None:
    """
    Render the main question-answer panel.

    Layout:
    - Horizontal rule separator.
    - Text input with placeholder and 200-character limit.
    - Live character counter caption.
    - "Ask" and "Clear" buttons side by side.
    - Empty-state message when no answer is stored in session state.
    - On submission: run the RAG pipeline, handle errors, persist results
      to session state, then render the answer and sidebar chunks.

    Session state management:
    - Uses ``clear_pending`` flag to reset the text_input widget on the
      next rerun (Streamlit prohibits writing to a widget key after the
      widget has rendered in the same run).
    - Stores the last answer, chunks, and metrics under ``last_answer``,
      ``last_chunks``, and ``last_metrics`` so results survive reruns.
    """
    # Apply the clear flag before the text_input widget is instantiated.
    # Setting the widget key directly after it has rendered causes a
    # StreamlitAPIException, so we reset it here via the pending flag.
    if st.session_state.get("clear_pending"):
        st.session_state["clear_pending"] = False
        st.session_state["question"] = ""

    st.markdown("---")

    question = st.text_input(
        "",
        placeholder="Ask a question about your documents…",
        max_chars=200,
        key="question",
    )

    # Live character counter (Req 8.4)
    char_count = len(question) if question else 0
    st.caption(f"{char_count} / 200")

    col_ask, col_clear = st.columns([1, 1], gap="small")
    submitted = col_ask.button("Ask", use_container_width=True)
    cleared = col_clear.button("Clear", use_container_width=True)

    # Handling "Clear": set the flag and rerun so the text_input resets
    # cleanly before the next widget tree is built.
    if cleared:
        st.session_state["clear_pending"] = True
        st.rerun()

    # Empty state — shown until the first successful answer is stored.
    if "last_answer" not in st.session_state:
        st.markdown(
            """
            <div style="text-align: center; padding: 40px 0; color: #5d6d7e;">
                <div style="font-size: 3em;">📄</div>
                <p style="font-size: 1.1em; margin-top: 8px;">Enter a question above to search your documents</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if submitted:
        if not question or not question.strip():
            st.warning("Please enter a question before submitting.")
        else:
            answer = None
            chunks = None
            metrics = None
            error_message = None

            # Run the full pipeline under a single spinner.
            # All rendering (st.error, render_answer, render_sidebar_chunks)
            # is deferred until after the spinner context exits so that
            # Streamlit flushes everything in one go on the same rerun.
            with st.spinner("Searching documents and generating answer…"):
                try:
                    answer, chunks, metrics = answer_question(question)
                except FileNotFoundError:
                    error_message = (
                        "Vector store not found. Run ingest.py first."
                    )
                except RuntimeError as exc:
                    error_message = str(exc)
                except ConnectionError:
                    error_message = (
                        "Ollama is unavailable. "
                        "Ensure it is running at localhost:11434."
                    )
                except ValueError:
                    # Empty/whitespace question — already guarded above, but
                    # handle defensively in case answer_question raises it.
                    error_message = (
                        "Please enter a question before submitting."
                    )
                except Exception:
                    error_message = (
                        "An unexpected error occurred. Please try again."
                    )

            if error_message is not None:
                st.error(error_message)
            else:
                # Persist results so they survive subsequent reruns
                # (e.g. user types another character in the input).
                st.session_state["last_answer"] = answer
                st.session_state["last_chunks"] = chunks
                st.session_state["last_metrics"] = metrics

    # Display whatever answer is in session state (from this or prior submit).
    if "last_answer" in st.session_state:
        render_answer(
            st.session_state["last_answer"],
            st.session_state["last_metrics"],
        )
        render_sidebar_chunks(st.session_state["last_chunks"])


# ---------------------------------------------------------------------------
# Startup sequence and entry point
# ---------------------------------------------------------------------------

# 2. Inject CSS overrides (dark theme, rounded inputs, card styles)
inject_custom_css()

# 3. Validate configuration constants; halt on ValueError
_validate_config_or_stop()

# 4. Verify vector store is present; halt with actionable message if not
_check_vector_store_or_stop()

# 5. Verify Ollama is reachable; halt with actionable message if not
_check_ollama_or_stop()

# 6. Hero header — gradient title + subtitle
render_hero_header()

# 7. Main panel — question input, submit logic, answer + sidebar
render_main_panel()
