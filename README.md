# MF Scheme FAQ RAG Chatbot

A facts-only Retrieval-Augmented Generation (RAG) chatbot that answers questions about **HDFC Mutual Fund** schemes using public scheme pages. Every answer carries exactly one source link. The assistant refuses investment-advice questions.

> **Disclaimer shown in the UI:** "Facts-only. No investment advice."

---

## Scope

- **AMC:** HDFC Mutual Funds
- **Schemes:** HDFC Large Cap Fund (Direct, Growth), HDFC Equity Fund – Flexi Cap (Direct, Growth), HDFC ELSS Tax Saver Fund (Direct, Growth), HDFC Mid Cap Fund (Direct, Growth), plus the AMC overview page and the AMFI investor page
- **Corpus:** 6 public pages (see `data/sources.md`)
- **Out of scope:** personalised advice, returns comparison, live NAV, multiple AMCs, user accounts, PII of any kind

---

## Tech stack

| Component | Choice |
|---|---|
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` (HuggingFace, runs locally — no API key) |
| Vector DB | ChromaDB (persistent, cosine space) |
| Chunking | Paragraph/sentence-aware, ~800 chars, ~100 char overlap |
| Retrieval | Hybrid: dense cosine candidates re-ranked by a row-aware lexical pass |
| Generation | **Groq API** — `openai/gpt-oss-120b` (OpenAI optional fallback, extractive fallback if no key) |
| UI | Streamlit |

> Note on the API boundary: Groq is used **only for answer generation**. Embeddings and retrieval are fully local (HuggingFace model + ChromaDB), as specified in the PRD.

---

## Project structure

```
├── docs/                     PRD.md, architecture.md, implementation.md, problemstatement.txt
├── data/sources.md           corpus URLs + blocked-source record
├── src/
│   ├── ingestion/            loader.py, chunker.py, embedder.py, vector_store.py, run_ingest.py
│   ├── retrieval/            retriever.py, prompts.py, test_retrieve.py
│   ├── guardrails.py         advice/refusal classifier
│   ├── generation.py         LLM answer generation + citation
│   ├── orchestrator.py       guardrails -> retrieval -> generation
│   ├── chat.py               terminal chat client
│   ├── make_sample_qa.py     regenerates sample_qa.md
│   └── app.py                Streamlit UI
├── chroma_db/                persisted vector store (generated)
├── notebooks/                optional demo notebook
├── sample_qa.md              sample Q&A output
├── requirements.txt
└── .env.example
```

---

## Setup

**1. Create a virtual environment**

```bash
python -m venv .venv
```

**2. Install dependencies** (use `.venv\Scripts\` on Windows, `.venv/bin/` on macOS/Linux)

```bash
.venv\Scripts\pip install -r requirements.txt
```

**3. Optional: add your Groq API key** (without it the app runs in extractive mode and quotes source text)

Get a free key from https://console.groq.com/keys

```bash
Copy-Item .env.example .env     # Windows
# cp .env.example .env          # macOS/Linux
```

Then edit `.env`:

```
GROQ_API_KEY="gsk-your-key-here"
GROQ_MODEL="openai/gpt-oss-120b"
```

Other models available on the free Groq tier: `openai/gpt-oss-20b`, `qwen/qwen3.8-27b`. Check the live list at https://console.groq.com/docs/models — decommissioned models (e.g. `llama3-8b-8192`) return a 400 error.

**4. Build the vector index** (only needed once, or when sources change)

```bash
.venv\Scripts\python.exe -m src.ingestion.run_ingest --step embed --reset
```

Expected output: `Upserted 84 records into 'mf_faq'`.

> If you get `PermissionError: chroma.sqlite3 is being used by another process`, close the Streamlit app or terminal chat, then re-run the command. The reset drops the ChromaDB collection rather than deleting the folder, which avoids the Windows file lock.

---

## Run

**Web UI**

```bash
.venv\Scripts\streamlit.exe run src/app.py
```

Open http://localhost:8501

If you get `ModuleNotFoundError: No module named 'src'`, run it via Python instead:

```bash
.venv\Scripts\python.exe -m streamlit run src/app.py
```

**Terminal only**

```bash
.venv\Scripts\python.exe -m src.orchestrator
.venv\Scripts\python.exe -m src.orchestrator "What is the exit load of HDFC Large Cap Fund?"
```

---

## Useful commands

| Command | Purpose |
|---|---|
| `python -m src.ingestion.run_ingest --step load` | Fetch and clean the 6 pages, print char counts |
| `python -m src.ingestion.run_ingest --step chunk` | Chunk and print sample chunks |
| `python -m src.ingestion.run_ingest --step embed --reset` | Full pipeline, rebuild the index |
| `python -m src.ingestion.run_ingest --step query --query "expense ratio of HDFC Mid Cap Fund"` | Inspect ranked chunks (uses the same retriever as the bot) |
| `python -m src.guardrails` | Run the advice-refusal test cases |
| `python -m src.retrieval.test_retrieve` | Inspect top-k chunks and the built prompt |
| `python -m src.chat` | Terminal chat session (`/quit` to exit) |
| `python -m src.make_sample_qa` | Regenerate `sample_qa.md` |

---

## How it works

1. **Ingestion (offline):** fetch pages → strip boilerplate → render tables as labelled `Column: value` rows → chunk on paragraph/sentence boundaries → embed with MiniLM → upsert into ChromaDB with `{source_url, scheme, amc, chunk_id}` metadata
2. **Retrieval + generation (online):**
   - `guardrails.is_advice_query()` — refuse advice/portfolio/comparison questions before any LLM call
   - `retriever.retrieve()` — embed the query, pull dense candidates from ChromaDB, then re-rank them with a row-aware lexical score (see below)
   - `generation.generate_answer()` — answer strictly from retrieved context, capped at 3 sentences, cite one URL
   - Relevance gate — if the top match scores below `0.25`, or the answer never mentions the term asked about, answer "not in my sources" instead of guessing

### Why retrieval is hybrid

The AMC overview page holds a table of ~15 HDFC schemes with columns like `Fund Name | Expense Ratio | NAV | Exit Load`. Two problems follow from that:

1. **Loading:** a flat text dump (`HDFC Flexi Cap Direct Plan-Growth 2,150.08 0.77 ...`) loses which number is which, so the expense ratio is unretrievable. The loader now emits `Fund Name: HDFC Flexi Cap Direct Plan-Growth | NAV: 2,150.08 | Expense Ratio: 0.77 | ...`.
2. **Ranking:** every row embeds almost identically, so dense similarity cannot tell them apart. The retriever splits table chunks on the `Fund Name:` marker, scores each row separately, and combines that with dense similarity, exact domain phrases ("expense ratio", "exit load"), and a spacing-insensitive scheme-name match.

Both are needed — labelling without the lexical re-rank left the right row ranked 6th; the re-rank without labelling had nothing to match on.

---

## Known limits

- **Corpus gaps.** `hdfcmf.com` (fees, factsheets, statement guides) and `hdfcaml.com` are unreachable from the demo network, so **ELSS lock-in, riskometer/benchmark, and statement-download questions have no supporting text**. The assistant reports "not in my sources" and links AMFI. Fix: from a network that can reach those hosts, add the URLs to `CORPUS` in `src/ingestion/loader.py` and re-run ingestion. See `data/sources.md` for the exact failure log.
- **HDFC Large Cap Fund is not in the AMC table.** The AMC overview lists "HDFC Large & Mid Cap Fund" but has no plain "Large Cap Fund" row, and the Large Cap page itself does not publish the expense ratio. So large-cap expense-ratio and lump-sum questions legitimately have no answer in this corpus — the "Large & Mid Cap" row (0.92) is deliberately *not* substituted for it.
- **Table facts are point-in-time.** Expense ratio, NAV, fund size and exit load come from a table snapshot at ingestion time. The answer always shows "Last updated from sources" for this reason.
- **Extractive mode without a working key.** If no key is set (or the API call fails), answers quote the most relevant source sentence and are prefixed `(extractive mode - showing source text)`. With `GROQ_API_KEY` set, answers are written in plain language instead.
- **Tuning knobs.** `MIN_SCORE`, `TOP_K`, `LEXICAL_BONUS`, `SCHEME_BOOST` and `CANDIDATE_POOL` are read from `.env`. `MIN_SCORE` too high makes the bot refuse valid questions; too low and it answers from an unrelated chunk.
- **No live data.** NAV, AUM and returns change daily; the index reflects the pages at ingestion time.
- **Keyword guardrails.** Advice detection is regex-based, so unusual phrasings may slip through; the system prompt is the second line of defence.
- **English only, single AMC.**

---

## Privacy

The app collects no personal data and stores no chat history. It does not accept or request PAN, Aadhaar, account numbers, OTPs, email addresses or phone numbers. Only public page text is embedded into the local ChromaDB.
