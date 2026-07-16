"""
app.py — Streamlit entry point for the RAG demo.

Provides a minimal web UI for the question-answering pipeline. Accepts a user
question, passes it to the RAG pipeline via answer_question(), and displays the
generated answer along with the retrieved document chunks.

Config validation runs at module startup before any UI is rendered. If config
is invalid, an error is displayed and the app halts.
"""

import time

import streamlit as st

from rag import answer_question
from config import validate_config

# Validate configuration before rendering any UI.
try:
    validate_config()
except ValueError as config_error:
    st.error(str(config_error))
    st.stop()

st.title("Intelligent Document Search")

# The Clear button sets a flag BEFORE the text_input widget is instantiated.
# Streamlit prohibits writing to a session state key after its widget has
# already rendered in the same run, so we use a separate "clear_pending" flag
# to signal that the input value should be reset on this run.
if st.session_state.get("clear_pending"):
    st.session_state["clear_pending"] = False
    st.session_state["question"] = ""

question = st.text_input("Your question:", max_chars=200, key="question")

col_submit, col_clear = st.columns([1, 1], gap="small")
submitted = col_submit.button("Submit", use_container_width=True)
cleared = col_clear.button("Clear", use_container_width=True)

if cleared:
    # Set the flag so the next rerun resets the input before rendering it.
    st.session_state["clear_pending"] = True
    st.rerun()

if submitted:
    if not question or not question.strip():
        st.warning("Please enter a question before submitting.")
    else:
        answer = None
        retrieved_chunks = None
        elapsed_seconds = None
        error_message = None

        # All rendering (st.write, st.error, st.caption) is kept outside the
        # spinner block. Streamlit batches render calls made inside a spinner
        # context and only flushes them on the next rerun. Collecting results
        # into plain variables inside the spinner, then rendering after it
        # exits, ensures output appears on the same run that produced it.
        with st.spinner("Thinking..."):
            start_time = time.monotonic()
            try:
                answer, retrieved_chunks = answer_question(question)
            except FileNotFoundError:
                error_message = "Vector store not found. Run ingest.py first."
            except RuntimeError:
                error_message = "Vector store is empty. Re-run ingest.py with valid PDF files."
            except ConnectionError:
                error_message = "Ollama is unavailable. Ensure it is running at localhost:11434."
            except Exception:
                error_message = "An unexpected error occurred. Please try again."
            finally:
                elapsed_seconds = time.monotonic() - start_time

        if error_message is not None:
            st.error(error_message)

        if answer is not None:
            st.write(answer)
            st.caption(f"Generated in {elapsed_seconds:.1f}s")

        if retrieved_chunks is not None:
            with st.expander("Retrieved Chunks"):
                for i, chunk in enumerate(retrieved_chunks):
                    st.markdown(f"**Chunk {i+1}** — Source: `{chunk.metadata.get('source', 'unknown')}`")
                    st.write(chunk.page_content)
                    st.divider()
