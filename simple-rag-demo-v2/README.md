# 🔍 Intelligent Document Search v2

> An enhanced local RAG pipeline with hierarchical chunking, BGE embeddings, hybrid BM25+FAISS retrieval, and cross-encoder re-ranking. Runs fully locally with Ollama, or with Groq cloud inference for fast generation without a GPU.

A local RAG pipeline built entirely with open-source tools — no cloud, no GPU required. Built as a learning resource, it prioritises transparency at every level: the code exposes every pipeline stage explicitly, and the built-in observability layer records what each stage costs at runtime.

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/) [![LangChain](https://img.shields.io/badge/LangChain-0.3-1C3C3C?style=flat&logo=chainlink&logoColor=white)](https://python.langchain.com/) [![Streamlit](https://img.shields.io/badge/Streamlit-1.35+-FF4B4B?style=flat&logo=streamlit&logoColor=white)](https://streamlit.io/) [![BGE](https://img.shields.io/badge/BGE-bge--base--en--v1.5-0057FF?style=flat)](https://huggingface.co/BAAI/bge-base-en-v1.5) [![Ollama](https://img.shields.io/badge/Ollama-local%20LLM-black?style=flat)](https://ollama.com/) [![Groq](https://img.shields.io/badge/Groq-cloud%20LLM-F55036?style=flat)](https://console.groq.com/) [![License](https://img.shields.io/badge/License-MIT-green?style=flat)](LICENSE)

---

## Pipeline Observability

One of the goals of this project is to make a RAG pipeline fully transparent — not just in code, but at runtime. Every query generates a structured timing log that breaks the pipeline down into 10 named stages, making it straightforward to answer the question every RAG developer eventually asks: *where is the time actually going?*

### What gets measured

Every call to `answer_question()` times each of the following stages independently using `time.monotonic()`:

| Stage | What it measures |
|---|---|
| `index_load_s` | FAISS index, BM25 index, and chunk list deserialised from disk |
| `bge_model_load_s` | BGE embedding model (`BAAI/bge-base-en-v1.5`) initialised |
| `query_embed_s` | User question encoded into a dense vector |
| `faiss_search_s` | Top-K candidates retrieved from the FAISS vector index |
| `bm25_score_s` | Top-K candidates scored and ranked by BM25 keyword index |
| `rrf_mmr_s` | RRF fusion, MIN_SCORE filter, and MMR diversity selection |
| `cross_encoder_load_s` | Cross-encoder re-ranker model initialised |
| `cross_encoder_rank_s` | All candidates scored jointly against the query |
| `llm_generate_s` | LLM generates the final answer (Ollama local or Groq cloud) |
| `total_s` | Full end-to-end wall-clock time |

### Where results appear

**Terminal** — after every query a human-readable table is printed:
```
Timing breakdown:
  index_load_s              :  3.5991 s
  bge_model_load_s          :  2.7235 s
  query_embed_s             :  0.1073 s
  faiss_search_s            :  0.0878 s
  bm25_score_s              :  0.0064 s
  rrf_mmr_s                 :  0.0198 s
  cross_encoder_load_s      :  2.1731 s
  cross_encoder_rank_s      :  0.8713 s
  llm_generate_s            : 45.1621 s   ← Ollama local (CPU)
  total_s                   : 54.7504 s

# With Groq:
  llm_generate_s            :  1.7360 s   ← Groq cloud (26× faster)
  total_s                   : 10.8220 s
```

**UI** — two metric cards show the two slowest stages automatically, and a collapsible "⏱ Timing Breakdown" expander below the answer shows all 10 stages.

**Log file** — every query appends one JSON line to `logs/rag_timings.jsonl`:
```json
{
  "timestamp": "2026-07-25T19:20:19.286694+00:00",
  "question": "List the common challenges in deploying machine learning...",
  "index_load_s": 3.5991,
  "bge_model_load_s": 2.7235,
  "query_embed_s": 0.1073,
  "faiss_search_s": 0.0878,
  "bm25_score_s": 0.0064,
  "rrf_mmr_s": 0.0198,
  "cross_encoder_load_s": 2.1731,
  "cross_encoder_rank_s": 0.8713,
  "llm_generate_s": 45.1621,
  "total_s": 54.7504,
  "status": "ok",
  "error_type": null,
  "error_message": null
}
```

The log file is append-only across sessions, so timing data accumulates as you test different questions, chunk sizes, and model configurations.

### What this teaches

The timing data from a real run on an i5-6600 / 16 GB RAM / no GPU machine reveals a pattern that is common in local RAG deployments:

- **LLM generation dominates on CPU** — 45s out of 55s total (82%) is pure CPU token generation with Ollama. Switching to Groq reduces `llm_generate_s` to ~1.7s (26× faster) — the same pipeline, different execution environment.
- **Model re-initialisation is avoidable** — `index_load_s` + `bge_model_load_s` + `cross_encoder_load_s` add up to ~8.5s of overhead that repeats on every query. Caching these in `st.cache_resource` would eliminate this cost entirely.
- **Retrieval itself is fast** — `faiss_search_s` + `bm25_score_s` + `rrf_mmr_s` together take under 0.15s. The hybrid retrieval pipeline adds negligible latency.

This kind of evidence-based analysis is only possible when the pipeline is instrumented. The observability layer makes it straightforward to distinguish between *this is slow because of hardware* and *this is slow because of a design choice* — a distinction that matters when deciding what to optimise next.

### Reading the log file

To inspect all recorded queries:
```bash
python -c "
import json
from pathlib import Path
for line in Path('logs/rag_timings.jsonl').read_text(encoding='utf-8').strip().splitlines():
    entry = json.loads(line)
    print(f\"{entry['timestamp'][:19]}  total={entry['total_s']:.1f}s  llm={entry['llm_generate_s']:.1f}s  q={entry['question'][:60]}\")
"
```

---

## What's Changed from v1

| Area | Enhancement |
|---|---|
| **Extraction** | `pdfplumber` for layout-aware text and table extraction; section boundary detection; header/footer stripping |
| **Chunking** | Hierarchical parent-child chunking with document-aware overlap reset |
| **Embeddings** | `BAAI/bge-base-en-v1.5` with asymmetric BGE query/passage prefixes |
| **Retrieval** | Hybrid BM25 + FAISS with RRF fusion, MIN_SCORE filtering, and MMR deduplication |
| **Re-ranking** | Cross-encoder (`ms-marco-MiniLM-L-6-v2`) with parent content substitution |
| **Observability** | 10-span `time.monotonic()` timing, JSONL log, dynamic UI metric cards |
| **UI** | Wide layout, dark theme, hero header, sidebar chunk cards with score indicators |
| **Index** | Incremental update support — add documents without a full rebuild |
| **LLM** | Optional Groq integration — set `GROQ_API_KEY` to use cloud inference instead of local Ollama |

---

## Hardware Considerations

**Target hardware:** Intel i5-6600 (4-core), 16 GB DDR4 RAM, no GPU — all inference runs on CPU.

This pipeline is designed to run entirely on modest hardware. The trade-off for zero GPU cost is longer processing times, particularly for first-time ingestion and LLM generation. The table below gives realistic expectations for planning and benchmarking.

| Stage | Expected time (i5-6600 / 16 GB RAM) | Notes |
|---|---|---|
| First ingestion (3 PDFs, ~150 pages) | 8–12 minutes | BGE-base downloads ~420 MB on first run |
| Subsequent ingestion (same docs) | 5–8 minutes | Model already cached |
| Retrieval + re-ranking | 20–35 seconds | FAISS search fast; cross-encoder adds ~2–4 s |
| LLM generation (llama3.2 3B) | 30–60 seconds | 4-core CPU, no GPU acceleration |
| End-to-end query | ~1–1.5 minutes | First query may be slower due to model loading |

> For faster generation, `mistral` (4 GB) or `llama3.1:8b` (5 GB) can be substituted in `config.py`, but will require more RAM and increase generation time on this hardware.

---

## How It Works

```
PDF files → pdfplumber extraction → section detection → hierarchical chunking → BGE embeddings → FAISS + BM25 index
                                                                                                         ↓
User question → BGE query embed → Hybrid FAISS+BM25 search → RRF fusion → Score filter → MMR → Cross-encoder rerank → Parent substitution → Ollama LLM → Answer
```

Two workflows run independently:

| Workflow | Command | When to run |
|---|---|---|
| **Ingestion** (offline) | `python ingest.py` | Once per document set, or after adding/changing PDFs |
| **Question Answering** (online) | `streamlit run app.py` | Any time after ingestion |

---

## Tech Stack

| Layer | Tool | Purpose |
|---|---|---|
| UI | Streamlit | Wide-layout web interface with dark theme |
| Orchestration | LangChain | Pipeline building blocks and Document types |
| PDF extraction | `pdfplumber` | Layout-aware text and table extraction |
| Embeddings | `BAAI/bge-base-en-v1.5` | High-quality semantic text-to-vector encoding |
| Vector store | FAISS (`faiss-cpu`) | Fast dense similarity search over child chunks |
| Keyword index | `rank-bm25` (BM25Okapi) | Keyword-based retrieval for exact term matching |
| Re-ranker | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Joint query+passage scoring for final ranking |
| LLM (local) | Ollama (llama3.2) | Local answer generation, no internet required |
| LLM (cloud) | Groq (`llama-3.1-8b-instant`) | Optional — set `GROQ_API_KEY` for 26× faster generation |

---

## Project Structure

```
simple-rag-demo-v2/
├── app.py              # Streamlit web interface
├── ingest.py           # PDF ingestion: extract → chunk → embed → index
├── rag.py              # Query pipeline: retrieve → rerank → generate
├── prompts.py          # Prompt templates
├── config.py           # All tunable constants
├── requirements.txt    # Pinned Python dependencies
├── documents/          # Place your PDF files here
├── vectorstore/        # Auto-generated indexes (do not edit)
└── .streamlit/
    └── config.toml     # Dark theme configuration
```

---

## Prerequisites

**System requirements:**

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.12+ | [python.org/downloads](https://www.python.org/downloads/) |
| Git | any | [git-scm.com](https://git-scm.com/) |
| Ollama | latest | [ollama.com/download](https://ollama.com/download) — optional if using Groq |
| Disk space | ~4 GB | Embedding model (~420 MB), cross-encoder (~90 MB), LLM (~2 GB if using Ollama) |

**Supported platforms:** macOS 12+, Ubuntu 20.04+, Windows 10/11

> On Windows, Ollama installs as a background service and starts automatically. You do not need to run `ollama serve` manually.

**Pre-download the ML models** (optional — both download automatically on first use, but doing this step before ingestion avoids a mid-run wait):

```bash
# Download the BGE embedding model (~420 MB, runs on first ingestion automatically)
python -c "from langchain_community.embeddings import HuggingFaceEmbeddings; HuggingFaceEmbeddings(model_name='BAAI/bge-base-en-v1.5', model_kwargs={'device': 'cpu'})"

# Download the cross-encoder re-ranker (~90 MB, runs on first query automatically)
python -c "from sentence_transformers import CrossEncoder; CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')"
```

---

## Quickstart

### Step 1 — Install Ollama

<details>
<summary><b>macOS</b></summary>

```bash
brew install ollama
```
Or download the `.app` installer from [ollama.com/download](https://ollama.com/download).
</details>

<details>
<summary><b>Linux</b></summary>

```bash
curl -fsSL https://ollama.com/install.sh | sh
```
</details>

<details>
<summary><b>Windows</b></summary>

Download and run the installer from [ollama.com/download](https://ollama.com/download). Ollama starts automatically as a background service after installation — no need to run `ollama serve`.

If `ollama` is not recognised after install, open a new terminal window to pick up the updated PATH.
</details>

Verify:
```bash
ollama --version
```

---

### Step 2 — Pull the LLM

```bash
ollama pull llama3.2
```

Downloads the model weights (~2 GB). Runs once; cached locally after that. To use a different model, see [Tuning for Better Responses](#tuning-for-better-responses).

---

### Step 2b — Groq (optional — skip if using Ollama)

Groq provides free cloud inference with no GPU required. Generation is ~26× faster than local Ollama on CPU hardware.

1. Get a free API key at [console.groq.com](https://console.groq.com) — no credit card required.
2. Set the environment variable before launching the app:

**Windows PowerShell:**
```powershell
$env:GROQ_API_KEY="your-key-here"
$env:OLLAMA_MODEL="llama-3.1-8b-instant"
```

**macOS / Linux:**
```bash
export GROQ_API_KEY="your-key-here"
export OLLAMA_MODEL="llama-3.1-8b-instant"
```

Available Groq models (set via `OLLAMA_MODEL` environment variable):

| Model | Groq ID | Notes |
|---|---|---|
| Llama 3.1 8B | `llama-3.1-8b-instant` | Fastest, recommended |
| Llama 3.3 70B | `llama-3.3-70b-versatile` | Strongest quality |
| Llama 3.2 3B | `llama-3.2-3b-preview` | Lightest |
| Mixtral 8x7B | `mixtral-8x7b-32768` | Good for technical documents |

> When `GROQ_API_KEY` is set, Ollama does not need to be running. The app detects the key automatically and routes generation to Groq.

---

### Step 3 — Get the Project

You only need the `simple-rag-demo-v2/` folder — there is no need to clone the entire repository.

```bash
git clone --filter=blob:none --sparse https://github.com/<your-username>/Enterprise-AI-Solutions.git
cd Enterprise-AI-Solutions
git sparse-checkout set simple-rag-demo-v2
cd simple-rag-demo-v2
```

> **What this does:** `--sparse` with `--filter=blob:none` performs a partial clone — only the `simple-rag-demo-v2/` directory is downloaded. Other projects in the repository are not fetched.

---

### Step 4 — Create a Virtual Environment

**macOS / Linux**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell)**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**Windows (Command Prompt)**
```cmd
python -m venv .venv
.venv\Scripts\activate
```

You should see `(.venv)` in your prompt.

---

### Step 5 — Install Dependencies

```bash
pip install -r requirements.txt
```

First install takes a few minutes. All versions are pinned for reproducibility. Key additions over v1: `pdfplumber`, `rank-bm25`, `sentence-transformers`, and `faiss-cpu`.

> On first ingestion, the BGE embedding model (~420 MB) downloads automatically. On first query, the cross-encoder (~90 MB) downloads automatically. Both are cached in `~/.cache/huggingface/` after that.

---

### Step 6 — Add PDF Documents

Place your PDFs in the `documents/` directory:

```
documents/
├── annual-report.pdf
├── technical-spec.pdf
└── research-paper.pdf
```

Subdirectories are supported — all `.pdf` files are discovered recursively.

---

### Step 7 — Run the Ingestion Pipeline

```bash
python ingest.py
```

Expected output:
```
Extracting PDFs...
  Extracted 150 page(s) from 3 file(s)
Building parent and child chunks...
  Produced 420 child chunk(s) from 85 parent chunk(s)
Embedding child chunks (BGE)...
Building FAISS index...
Building BM25 index...
Saving indexes to vectorstore/...
Ingestion complete.
```

> BGE-base (`BAAI/bge-base-en-v1.5`) downloads ~420 MB from HuggingFace on the very first run. Subsequent runs use the local cache. Expect 8–12 minutes on i5-class hardware.

To add new documents without rebuilding from scratch:
```bash
python ingest.py --incremental
```

---

### Step 8 — Start Ollama

> Skip this step if you set `GROQ_API_KEY` in Step 2b — Ollama is not required when using Groq.

**macOS / Linux** — run in a separate terminal:
```bash
ollama serve
```

**Windows** — Ollama is already running as a background service after installation.

Verify it is reachable:
```bash
curl http://localhost:11434
```
Expected: `Ollama is running`

---

### Step 9 — Launch the App

```bash
streamlit run app.py
```

Open the printed URL in your browser (default: `http://localhost:8501`).

---

### Step 10 — Stopping the App

Press **Ctrl+C** in the terminal where Streamlit is running.

> On Windows, if Ctrl+C does not respond, close the terminal window directly. Your documents and vector store are unaffected.

---

## Using the App

1. Type a question (up to 200 characters) into the input field. A live character counter shows your remaining space.
2. Click **Ask**.
3. A spinner shows "Retrieving chunks…" while BM25+FAISS hybrid search and re-ranking run, then switches to "Generating answer…" during LLM inference.
4. The generated answer appears in a styled card with a left accent border.
5. Retrieval time and generation time are shown as metric cards — useful for identifying pipeline bottlenecks.
6. The left sidebar displays the top retrieved chunks, each with a source filename badge and a colour-coded relevance score (green ≥ 0.80, orange 0.50–0.79, red < 0.50).

**Example questions:**
- *"What are the key compliance requirements described in this document?"*
- *"Summarise the main risks identified."*
- *"What recommendations does the document make for securing cloud workloads?"*

---

## Updating Your Documents

To add new documents incrementally (without a full rebuild):

1. Add the new PDFs to `documents/`.
2. Run:
   ```bash
   python ingest.py --incremental
   ```

To rebuild the index from scratch (e.g., after removing or replacing documents):

1. Stop the app (`Ctrl+C`).
2. Update files in `documents/`.
3. Re-run ingestion:
   ```bash
   python ingest.py
   ```
4. Restart the app:
   ```bash
   streamlit run app.py
   ```

---

## Configuration

All parameters live in `config.py`. No other file needs editing for basic configuration.

```python
# Embedding model
EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"

# LLM model name — used by both Ollama and Groq.
# For Ollama: "llama3.2", "mistral", "llama3.1:8b"
# For Groq:   "llama-3.1-8b-instant", "llama-3.3-70b-versatile"
# Override at runtime: set OLLAMA_MODEL environment variable
OLLAMA_MODEL    = "llama3.2"

# Directories
DOCUMENTS_DIR   = "documents"
VECTORSTORE_DIR = "vectorstore"

# Chunking
CHILD_CHUNK_SIZE    = 400    # Characters per child chunk (indexed for retrieval)
CHILD_CHUNK_OVERLAP = 80     # Overlap between consecutive child chunks (resets at section boundaries)
PARENT_CHUNK_SIZE   = 1500   # Characters per parent chunk (passed to the LLM)

# Retrieval
CANDIDATE_K = 20    # Number of candidates fetched from FAISS and BM25 before re-ranking
TOP_K       = 5     # Number of re-ranked chunks passed to the LLM
MIN_SCORE   = 0.30  # Minimum FAISS cosine similarity; candidates below this are discarded
```

> After changing `CHILD_CHUNK_SIZE`, `CHILD_CHUNK_OVERLAP`, `PARENT_CHUNK_SIZE`, or `EMBEDDING_MODEL`, re-run `python ingest.py` to rebuild the vector store.

---

## Tuning for Better Responses

If answers feel vague, off-topic, or incomplete, these are the main levers — listed in order of typical impact.

### 1. TOP_K — chunks passed to the LLM

**File:** `config.py` &nbsp;|&nbsp; **Re-ingestion required:** No

`TOP_K` controls how many re-ranked parent-context chunks the LLM sees. If the relevant passage is not in the top-N, the model cannot answer correctly.

| Value | Effect |
|---|---|
| `5` (default) | Fast; covers most queries on focused documents |
| `6`–`8` | Broader context; recommended starting point for longer documents |
| `10` | Maximum practical recall; slower and may dilute focus |

✅ **Try first:** `TOP_K = 7`

---

### 2. MIN_SCORE — similarity threshold

**File:** `config.py` &nbsp;|&nbsp; **Re-ingestion required:** No

Controls the minimum cosine similarity a candidate must have to enter re-ranking. Raising this improves precision but may discard borderline-relevant chunks.

| Value | Effect |
|---|---|
| `0.20` | More permissive; useful for broad or vague queries |
| `0.30` (default) | Balanced |
| `0.45`–`0.50` | High precision; may over-filter on short or paraphrased queries |

✅ **Try first:** Lower to `MIN_SCORE = 0.20` if answers are missing expected content.

---

### 3. CHILD_CHUNK_SIZE — retrieval granularity

**File:** `config.py` &nbsp;|&nbsp; **Re-ingestion required:** Yes

Smaller child chunks improve retrieval precision for specific facts. Larger chunks keep more context together but may blend topics.

| Value | Best for |
|---|---|
| `200`–`300` | Dense technical documents, short factual lookups |
| `400` (default) | General technical documents |
| `600`–`800` | Longer narrative documents where context matters more than precision |

✅ **Try first:** `CHILD_CHUNK_SIZE = 300` for highly specific questions.

---

### 4. PARENT_CHUNK_SIZE — LLM context window

**File:** `config.py` &nbsp;|&nbsp; **Re-ingestion required:** Yes

After re-ranking, the LLM receives the parent chunk (full section) rather than the small child fragment. A larger parent means more context — useful when the answer spans several paragraphs.

| Value | Effect |
|---|---|
| `1000` | Tighter focus; faster prompt construction |
| `1500` (default) | Balanced section coverage |
| `2500`+ | Broad context; may dilute focus for targeted questions |

---

### 5. CANDIDATE_K — retrieval pool size

**File:** `config.py` &nbsp;|&nbsp; **Re-ingestion required:** No

How many candidates are pulled from FAISS and BM25 before re-ranking. A larger pool improves recall at the cost of re-ranking time.

| Value | Effect |
|---|---|
| `10` | Fast; sufficient for small document sets |
| `20` (default) | Balanced |
| `30`–`50` | Higher recall for large document sets; noticeable re-ranking overhead |

---

### 6. LLM — the language model

**File:** `config.py` / environment variable `OLLAMA_MODEL` &nbsp;|&nbsp; **Re-ingestion required:** No

**Ollama (local)** — runs on CPU, no internet required:

| Model | Download size | Notes |
|---|---|---|
| `llama3.2` (default) | ~2 GB | Fast; good for simple lookups |
| `mistral` | ~4 GB | Better reasoning; recommended for technical documents |
| `llama3.1:8b` | ~5 GB | Strong general-purpose model; requires ~12 GB RAM |

```bash
ollama pull mistral
```

**Groq (cloud, free tier)** — set `GROQ_API_KEY` to activate; ~26× faster than local CPU:

| Model | Groq ID | Speed |
|---|---|---|
| Llama 3.1 8B | `llama-3.1-8b-instant` | Fastest |
| Llama 3.3 70B | `llama-3.3-70b-versatile` | Best quality |
| Mixtral 8x7B | `mixtral-8x7b-32768` | Good for technical docs |

```powershell
$env:GROQ_API_KEY="your-key-here"
$env:OLLAMA_MODEL="llama-3.1-8b-instant"
```

> The pipeline automatically uses Groq when `GROQ_API_KEY` is set and falls back to Ollama when it is not.

---

### Recommended config for technical documents

```python
# config.py
CHILD_CHUNK_SIZE    = 300
CHILD_CHUNK_OVERLAP = 60
PARENT_CHUNK_SIZE   = 1500
CANDIDATE_K         = 25
TOP_K               = 7
MIN_SCORE           = 0.25
```

Re-run `python ingest.py` after changing chunking parameters, then restart the app.

---

## Troubleshooting

<details>
<summary><b>documents/ directory not found or contains no PDF files</b></summary>

The `documents/` directory is empty or missing. Add at least one PDF and re-run `python ingest.py`.
</details>

<details>
<summary><b>Vector store not found. Run ingest.py first.</b></summary>

Ingestion has not been run yet, or was run from a different directory. Run `python ingest.py` from the project root.
</details>

<details>
<summary><b>Ollama is unavailable. Ensure it is running at localhost:11434.</b></summary>

Ollama is not running. On macOS/Linux, start it with `ollama serve`. On Windows, launch from the Start menu or check the system tray. Verify with `curl http://localhost:11434`.
</details>

<details>
<summary><b>Error: model 'llama3.2' not found</b></summary>

The model has not been pulled. Run `ollama pull llama3.2` (or whichever model is set in `config.py`).
</details>

<details>
<summary><b>Embedding model download is slow or fails</b></summary>

`BAAI/bge-base-en-v1.5` downloads ~420 MB from HuggingFace on first run. Ensure you have an internet connection. Subsequent runs use the cache at `~/.cache/huggingface/`.
</details>

<details>
<summary><b>streamlit: command not found</b></summary>

The virtual environment is not active. Run the activate command from Step 4 before starting Streamlit.
</details>

<details>
<summary><b>Port 8501 is already in use</b></summary>

Run on a different port:
```bash
streamlit run app.py --server.port 8502
```
</details>

<details>
<summary><b>ollama is not recognised after installation on Windows</b></summary>

The PATH update from the installer only takes effect in new terminal sessions. Close your current terminal, open a new one, and retry `ollama --version`.
</details>

<details>
<summary><b>No relevant chunks found above the minimum similarity threshold.</b></summary>

The query did not match any chunks with a similarity score at or above `MIN_SCORE`. Lower `MIN_SCORE` in `config.py` (try `0.20`) and re-run the query. If the issue persists, ensure the relevant PDFs are in `documents/` and that ingestion has been re-run after adding them.
</details>

<details>
<summary><b>Error: model 'llama3.2' does not exist on Groq</b></summary>

Groq uses different model IDs from Ollama. Set `OLLAMA_MODEL` to a valid Groq model ID, e.g. `llama-3.1-8b-instant`. See the model table in [Step 2b](#step-2b--groq-optional--skip-if-using-ollama).
</details>

<details>
<summary><b>Groq API key is set but the app still tries to use Ollama</b></summary>

The environment variable must be set in the same terminal session before launching the app. Close the terminal, open a new one, set `$env:GROQ_API_KEY`, then run `streamlit run app.py`.
</details>

<details>
<summary><b>Model not found in cache.</b></summary>

The BGE embedding model or cross-encoder is not present in the local HuggingFace cache, and the machine cannot reach HuggingFace. Run the model download commands from the [Prerequisites](#prerequisites) section on a machine with internet access, then copy the cache to the target machine.
</details>

---

## License

[MIT](LICENSE)
