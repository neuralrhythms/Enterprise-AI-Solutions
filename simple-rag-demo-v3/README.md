# 🔍 Intelligent Document Search v3

> Version 3 is an enhancement of the v2 RAG pipeline. This version has three major upgrades- 1. No local LLM or GPU required — Groq replaces Ollama for ~500 tokens/s generation on the free tier. 2. Observability dashboard provided by Langfuse. This replaces the custom logic for capturing timing traces. 3. UI now shows token usage and costs. 

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/) [![Groq](https://img.shields.io/badge/Groq-cloud%20LLM-F55036?style=flat)](https://console.groq.com/) [![Langfuse](https://img.shields.io/badge/Langfuse-observability-6366f1?style=flat)](https://langfuse.com/) [![Streamlit](https://img.shields.io/badge/Streamlit-1.35+-FF4B4B?style=flat&logo=streamlit&logoColor=white)](https://streamlit.io/) [![License](https://img.shields.io/badge/License-MIT-green?style=flat)](LICENSE)

---

## What's Changed from v2

| Area | Enhancement |
|---|---|
| **LLM** | Groq replaces local Ollama — `llama-3.1-8b-instant` via free-tier API (~500 tok/s vs ~2 tok/s on CPU) |
| **Observability** | Langfuse replaces the custom JSONL timing log — traces, spans, generation metrics, and user feedback scores |
| **No Ollama** | Ollama no longer required — no local model download, no 2 GB model file, no GPU needed |

---

## What Does Not Change from v2

- PDF extraction (`pdfplumber`, section detection, table handling)
- Hierarchical parent-child chunking
- BGE-base embeddings (local, CPU)
- Hybrid BM25 + FAISS retrieval with RRF fusion, MMR, score filtering
- Cross-encoder re-ranking (`ms-marco-MiniLM-L-6-v2`, local, CPU)
- Streamlit UI layout, hero header, sidebar chunk cards

---

## Pipeline

```
PDF files → pdfplumber → hierarchical chunking → BGE embeddings → FAISS + BM25 index
                                                                          ↓
User question → BGE embed → Hybrid FAISS+BM25 → RRF → MMR → Cross-encoder rerank → Groq LLM → Answer
                                                                                          ↓
                                                                                    Langfuse trace
```

---

## Tech Stack

| Layer | Tool | Purpose |
|---|---|---|
| UI | Streamlit | Wide-layout web interface with dark theme |
| PDF extraction | `pdfplumber` | Layout-aware text and table extraction |
| Embeddings | `BAAI/bge-base-en-v1.5` (local) | Semantic text-to-vector encoding |
| Vector store | FAISS (`faiss-cpu`) | Dense similarity search |
| Keyword index | `rank-bm25` | Exact term matching |
| Re-ranker | `cross-encoder/ms-marco-MiniLM-L-6-v2` (local) | Joint query+passage scoring |
| **LLM** | **Groq** (`llama-3.1-8b-instant`) | Cloud inference, free tier, ~500 tok/s |
| **Observability** | **Langfuse** | Traces, spans, generation metrics, user scores |

---

## Prerequisites

- Python 3.12+
- Groq API key — free at [console.groq.com](https://console.groq.com), no credit card required
- Langfuse — self-hosted via Docker or cloud account at [cloud.langfuse.com](https://cloud.langfuse.com)
- Docker Desktop — required for running Langfuse locally ([docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/))

---

## Quickstart

### Step 1 — Get the project

```bash
git clone --filter=blob:none --sparse https://github.com/<your-username>/Enterprise-AI-Solutions.git
cd Enterprise-AI-Solutions
git sparse-checkout set simple-rag-demo-v3
cd simple-rag-demo-v3
```

### Step 2 — Get a Groq API key

1. Go to [console.groq.com](https://console.groq.com) and sign up (free)
2. Create an API key
3. Set it as an environment variable:

**Windows PowerShell:**
```powershell
$env:GROQ_API_KEY="your-key-here"
```

**macOS / Linux:**
```bash
export GROQ_API_KEY="your-key-here"
```

### Step 3 — Create a virtual environment

**Windows PowerShell:**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Step 4 — Install dependencies

```bash
pip install -r requirements.txt
```

First install takes a few minutes. All versions are pinned for reproducibility.

### Step 5 — Add PDF documents

Place your PDFs in the `documents/` directory. Subdirectories are supported.

### Step 6 — Run ingestion

```bash
python ingest.py
```

Builds the FAISS + BM25 index from your PDFs. The BGE-base embedding model downloads ~420 MB on first run and is cached locally after that.

### Step 7 — Start Langfuse

**Self-hosted (local Docker, full data privacy):**
```bash
git clone https://github.com/langfuse/langfuse.git
cd langfuse
# Pin to v2 to match the langfuse Python SDK used in this project
# Edit docker-compose.yml: change langfuse:4 → langfuse:2 and langfuse-worker:4 → langfuse-worker:2
docker compose up -d
```
UI at `http://localhost:3000`. Create a project and copy the Public and Secret keys.

**Cloud (zero infrastructure):**
Sign up at [cloud.langfuse.com](https://cloud.langfuse.com).

Set environment variables:
```powershell
$env:LANGFUSE_PUBLIC_KEY="pk-lf-..."
$env:LANGFUSE_SECRET_KEY="sk-lf-..."
$env:LANGFUSE_HOST="http://localhost:3000"   # or https://cloud.langfuse.com
```

### Step 8 — Launch the app

```bash
streamlit run app.py
```

Open `http://localhost:8501`.

---

## Configuration

All parameters live in `config.py`. Override at runtime with environment variables — no file editing required.

```python
# LLM — GROQ_API_KEY is required
GROQ_API_KEY  = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL    = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")

# Langfuse — optional
LANGFUSE_PUBLIC_KEY = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = os.environ.get("LANGFUSE_SECRET_KEY", "")
LANGFUSE_HOST       = os.environ.get("LANGFUSE_HOST", "http://localhost:3000")

# Retrieval (tunable)
CANDIDATE_K = 20    # candidates before re-ranking
TOP_K       = 5     # chunks passed to LLM after re-ranking
MIN_SCORE   = 0.30  # minimum FAISS cosine similarity
```

### Groq model options

| Model | Groq ID | Notes |
|---|---|---|
| Llama 3.1 8B | `llama-3.1-8b-instant` | Fastest, default |
| Llama 3.3 70B | `llama-3.3-70b-versatile` | Best quality |
| Mixtral 8x7B | `mixtral-8x7b-32768` | Good for technical documents |

Switch model: `$env:GROQ_MODEL="llama-3.3-70b-versatile"`

---

## Langfuse Observability

When Langfuse keys are set, every query creates a trace with 9 named spans:

```
rag_query  [total ~8–12s]
├── index_load          [~3.5s — FAISS + BM25 loaded from disk]
├── bge_model_load      [~2.8s — BGE embedding model initialised]
├── query_embed         [~0.1s — question encoded]
├── faiss_search        [~0.08s]
├── bm25_score          [~0.005s]
├── rrf_mmr             [~0.02s]
├── cross_encoder_load  [~2.2s]
├── cross_encoder_rank  [~0.5s]
└── llm_generate        [~1.7s]  ← Groq (vs 45s with local Ollama on CPU)
```

The `llm_generate` stage uses a Langfuse **Generation** object so token counts and cost appear in the Langfuse dashboards automatically.

### Register the model for cost tracking

In the Langfuse UI → Settings → Models → Add model:

| Field | Value |
|---|---|
| Model name | `llama-3.1-8b-instant` |
| Match pattern | `llama-3.1-8b-instant` |
| Input cost per 1K tokens | `0.00000022` |
| Output cost per 1K tokens | `0.00000022` |

### User feedback

👍 / 👎 buttons appear below every answer and submit scores to the Langfuse Scores dashboard.

### Token usage in the UI

Prompt tokens, completion tokens, and estimated cost are shown as metric cards below each answer when Groq returns token data.

---

## Project Structure

```
simple-rag-demo-v3/
├── app.py              # Streamlit UI — Groq LLM, Langfuse trace link, feedback buttons
├── ingest.py           # PDF ingestion — extract → chunk → BGE embed → FAISS + BM25
├── rag.py              # Query pipeline — Groq generation, Langfuse spans
├── prompts.py          # Prompt templates
├── config.py           # All constants — reads from environment variables
├── requirements.txt    # Pinned dependencies
├── documents/          # Place your PDF files here
├── vectorstore/        # Auto-generated FAISS + BM25 index (do not edit)
└── .streamlit/
    └── config.toml     # Dark theme configuration
```

---

## Troubleshooting

<details>
<summary><b>GROQ_API_KEY is not set</b></summary>

The app halts at startup if `GROQ_API_KEY` is not set. Set it in the same terminal session before launching:
```powershell
$env:GROQ_API_KEY="your-key-here"
streamlit run app.py
```
</details>

<details>
<summary><b>Vector store not found. Run ingest.py first.</b></summary>

Run `python ingest.py` from the project root before launching the app.
</details>

<details>
<summary><b>Groq model not found (404)</b></summary>

The model ID is invalid for Groq. Set `GROQ_MODEL` to a valid Groq model ID — e.g. `llama-3.1-8b-instant`. See the model table above.
</details>

<details>
<summary><b>No Langfuse traces appearing</b></summary>

Check that both `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are set in the same terminal session as the app. Verify the Langfuse server is running and accessible at `LANGFUSE_HOST`. Check the terminal for `Langfuse flush failed` warnings.
</details>

<details>
<summary><b>Langfuse "Bad request" error</b></summary>

The `langfuse` Python SDK (v2) must match the server version (v2). If running Langfuse Docker, pin the server image to v2 by editing `docker-compose.yml`: change `langfuse:4` → `langfuse:2` and `langfuse-worker:4` → `langfuse-worker:2`, then run `docker compose down -v && docker compose up -d`.
</details>

<details>
<summary><b>Embedding model download is slow or fails</b></summary>

`BAAI/bge-base-en-v1.5` downloads ~420 MB from HuggingFace on first ingestion run. Ensure internet access. Subsequent runs use the cache at `~/.cache/huggingface/`.
</details>

<details>
<summary><b>No relevant chunks found above the minimum similarity threshold</b></summary>

Lower `MIN_SCORE` in `config.py` (try `0.20`) and re-run the query.
</details>

---

## License

[![License](https://img.shields.io/badge/License-MIT-green?style=flat)](LICENSE)
