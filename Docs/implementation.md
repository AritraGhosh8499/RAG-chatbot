# Implementation Plan — Phase-wise Guide

This document breaks the RAG FAQ chatbot into implementation phases. Each phase maps to `architecture.md` components and is sized to be handed to Cursor as a single, complete prompt. **Complete and test each phase before moving to the next.**

> **Reference docs:** `docs/PRD.md` (requirements), `docs/architecture.md` (design).
> **Tech:** Python, `sentence-transformers/all-MiniLM-L6-v2`, ChromaDB, Streamlit (or Gradio), one chat LLM API.

---

## Phase 0 — Project Bootstrap

**Goal:** Working Python environment and folder skeleton.

**Tasks:**
1. Create the folder structure from `architecture.md` §7 (`src/ingestion`, `src/retrieval`, `data/`, `notebooks/`, `docs/`).
2. Create `requirements.txt` with: `chromadb`, `sentence-transformers`, `beautifulsoup4`, `requests`, `streamlit`, `python-dotenv`, `openai` (or chosen LLM SDK), `lxml`.
3. Create a virtual environment, install dependencies, and verify imports work.
4. Create `.env.example` with `LLM_API_KEY=` placeholder; add `.env` to `.gitignore`.
5. Create `data/sources.md` listing the 5 corpus URLs from the PRD.

**Cursor prompt:**
> "Create the project structure per docs/architecture.md section 7, a requirements.txt, .env.example, and data/sources.md with the 5 URLs from docs/PRD.md. Do not write implementation code yet."

**Exit criteria:** `pip install -r requirements.txt` succeeds; folders exist; sources file has 5 URLs.

---

## Phase 1 — Data Ingestion: Loading

**Goal:** Fetch and clean the 5 pages into usable text. Maps to `architecture.md` §3, step 1.

**Tasks:**
1. Implement `src/ingestion/loader.py`:
   - `fetch_page(url: str) -> str` — HTTP GET with a browser-like User-Agent, timeout, and retry (2–3 attempts).
   - `clean_html(html: str) -> str` — parse with BeautifulSoup; remove `<script>`, `<style>`, `nav`, `footer`, `header`, forms; extract text from headings (`h1`–`h4`) and paragraphs/lists; collapse whitespace.
   - > Updated in Phase 9: tables are rendered as labelled `Column: value` rows rather than a flat cell dump, so facts like the expense ratio keep their column meaning.
   - `load_all(urls: list[str]) -> list[dict]` — returns `[{"url", "scheme", "text"}]` for each page.
2. Add a small manifest of the 5 URLs + scheme names (from `PRD.md`).
3. Write a smoke script `src/ingestion/run_ingest.py --step load` that prints per-URL character counts so you can confirm extraction isn't empty.

**Cursor prompt:**
> "Implement src/ingestion/loader.py per docs/implementation.md Phase 1. Use requests + BeautifulSoup, strip boilerplate, and return {url, scheme, text} per page. Add a --step load run script."

**Exit criteria:** All 5 URLs load and yield non-trivial text (>1k chars each); no scripts/styles in output.

---

## Phase 2 — Ingestion: Chunking

**Goal:** Split page text into semantically meaningful chunks. `architecture.md` §3, step 2.

**Tasks:**
1. Implement `src/ingestion/chunker.py`:
   - `chunk_text(text: str, max_chars=800, overlap=100) -> list[str]` — split on heading/paragraph boundaries first; merge small paragraphs until ~`max_chars`; apply a small character overlap between consecutive chunks.
   - `chunk_pages(pages: list[dict]) -> list[dict]` — returns `[{"text", "url", "scheme", "chunk_id"}]`.
2. Log chunk counts and average chunk size per page.
3. Sanity-print 2–3 chunks to eyeball quality (e.g., an expense-ratio section stays intact).

**Cursor prompt:**
> "Implement src/ingestion/chunker.py per Phase 2. Paragraph/heading-aware chunking, ~500–800 chars, ~100 chars overlap, preserve url/scheme metadata, deterministic chunk ids."

**Exit criteria:** Chunks are bounded in size; metadata preserved; a factual fact (e.g., expense ratio) appears fully inside at least one chunk.

---

## Phase 3 — Ingestion: Embeddings + Vector Store

**Goal:** Embed chunks and persist them in ChromaDB. `architecture.md` §3, steps 3–4 and §6 schema.

**Tasks:**
1. Implement `src/ingestion/embedder.py`:
   - Load `sentence-transformers/all-MiniLM-L6-v2` once (module-level singleton).
   - `embed_texts(texts: list[str]) -> list[list[float]]` (batched).
2. Implement `src/ingestion/vector_store.py`:
   - Create a persistent ChromaDB client at `./chroma_db`, collection e.g. `mf_faq`.
   - `upsert_chunks(chunks)` — id `{scheme_slug}_chunk_{id}`, metadata `{source_url, scheme, amc: "HDFC", chunk_id}`.
   - `query(embedding, k)` helper for later phases.
3. Extend `run_ingest.py` with `--step embed` (full pipeline: load → chunk → embed → upsert).
4. Print collection count at the end; expect roughly (total page text / avg chunk size) records.

**Cursor prompt:**
> "Implement embedder.py and vector_store.py per Phase 3, using sentence-transformers/all-MiniLM-L6-v2 and persistent ChromaDB. Wire a full ingestion run in run_ingest.py."

**Exit criteria:** `chroma_db/` directory created; record count > 0; querying with a sample embedding returns relevant chunks.

---

## Phase 4 — Guardrails (Advice Filter)

**Goal:** Refuse opinionated/portfolio questions before retrieval. `architecture.md` §4 step 1.

**Tasks:**
1. Implement `src/guardrails.py`:
   - `is_advice_query(query: str) -> bool` — keyword/pattern matching for intents like "should I buy", "should I sell", "is it a good time", "best fund for me", "recommend", "portfolio for me", "returns of X vs Y" (comparison).
   - `refusal_message()` — polite, facts-only message + one educational link (e.g., an AMC/AMFI investor-education page).
2. Add unit-style test block with 5–10 example queries (at least 3 must be refused, 3 must pass).

**Cursor prompt:**
> "Implement src/guardrails.py per Phase 4 with a conservative keyword/pattern classifier and a refusal message including an educational link. Include example test cases in the file."

**Exit criteria:** All 3 advice-like test queries are caught; factual queries pass through.

---

## Phase 5 — Retrieval + Prompt

**Goal:** Query → top-k chunks → grounded prompt. `architecture.md` §4 steps 2–4.

**Tasks:**
1. Implement `src/retrieval/retriever.py`:
   - `retrieve(query: str, k=4) -> list[dict]` — embed query with the same model, ChromaDB similarity search, return `{text, source_url, scheme, score}`.
   - > Updated in Phase 9: dense search alone could not separate the labelled table rows, so `retrieve()` re-ranks candidates with a row-aware lexical score. See Phase 9 for the final design.
2. Implement `src/retrieval/prompts.py`:
   - `SYSTEM_PROMPT` enforcing: facts-only, ≤3 sentences, no return computation/comparison, never invent facts, use only provided context, no PII.
   - `build_user_prompt(query, chunks)` — includes numbered context blocks with their source URLs.
3. Write `src/retrieval/test_retrieve.py` printing top chunks + scores for 3 sample queries.

**Cursor prompt:**
> "Implement retriever.py and prompts.py per Phase 5. Use the same embedding model as ingestion, k=4, and a strict facts-only system prompt."

**Exit criteria:** For each sample query, the top chunk is topically relevant; prompt text looks correct.

---

## Phase 6 — Answer Generation + Citation

**Goal:** LLM call producing answer + one citation. `architecture.md` §4 steps 5–6.

**Tasks:**
1. Implement `src/generation.py`:
   - `generate_answer(query, chunks) -> dict` — calls the chosen LLM with system + user prompt; returns `{"answer", "citation_url", "last_updated"}`.
   - Citation rule: `source_url` of the highest-ranked chunk.
   - `last_updated`: today's date (or source manifest date).
2. Implement `src/orchestrator.py`:
   - `ask(query)` — guardrails → (refusal OR retrieve → generate) → formatted response string:
     ```
     <answer>

     Source: <url>
     Last updated from sources: <date>
     ```
3. CLI test: `python -m src.orchestrator "What is the expense ratio of HDFC Mid Cap Fund?"`.

**Cursor prompt:**
> "Implement generation.py and orchestrator.py per Phase 6. Answers must be ≤3 sentences, include exactly one source link, and end with 'Last updated from sources:'."

**Exit criteria:** End-to-end CLI Q&A works for 3+ factual queries; advice query returns refusal; no invented facts observed.

---

## Phase 7 — UI

**Goal:** Tiny Streamlit UI per `PRD.md` §7.3.

**Tasks:**
1. Implement `src/app.py`:
   - Title + welcome line.
   - Static note: **"Facts-only. No investment advice."**
   - 3 clickable example questions that populate the input.
   - Chat-style input; on submit, call `orchestrator.ask()` and render answer, citation link, and last-updated line.
   - No message persistence, no login, no PII fields.
2. Run `streamlit run src/app.py` and exercise all sample queries manually.

**Cursor prompt:**
> "Build src/app.py in Streamlit per Phase 7: welcome line, disclaimer note, 3 example questions, chat input, rendered answer + citation + last-updated. No storage or auth."

**Exit criteria:** Demo flow works end-to-end in the browser; refusals render correctly.

---

## Phase 8 — Deliverables & Hardening

**Goal:** Fulfill the PRD deliverables list.

**Tasks:**
1. `sample_qa.md` — run 8–10 queries through `orchestrator.ask()`; paste query, answer, citation.
2. `data/sources.md` — finalized 5 URLs (already started).
3. `README.md` — setup steps, scope (HDFC + 4 schemes), run instructions (ingest → app), known limits.
4. Disclaimer snippet documented and mirrored in the UI.
5. Optional: re-run ingestion on a fresh `./chroma_db` to verify reproducibility.

**Cursor prompt:**
> "Create sample_qa.md with 8–10 query/answer/citation triples, finalize data/sources.md, and write README.md with setup, scope, and known limits per Phase 8."

**Exit criteria:** All PRD §10 deliverables exist; a fresh clone can follow README to reproduce the demo.

---

## Phase 9 — Retrieval Hardening (added after the Phase 8 demo test)

**Goal:** Make table-derived facts (expense ratio, NAV, exit load) answerable. Phase 8 shipped a working pipeline, but the demo questions "What is the expense ratio of HDFC Flexi Cap Fund?" and "What is the expense ratio of HDFC Mid Cap Fund?" both failed. Root cause and fix below.

### Symptom

Every fund row on the AMC overview page is a near-identical string of numbers, so:

1. the loader flattened tables into bare values (`HDFC Flexi Cap Direct Plan-Growth 2,150.08 0.77 ...`), losing which column each number belonged to, and
2. dense similarity could not separate one row from another — all rows embedded close together, so the row holding the answer never reliably reached the top-k.

### Fix 1 — Label table rows at load time (`src/ingestion/loader.py`)

`_table_to_text()` reads the header row, then emits each data row as `Column: value` pairs:

```
Table columns: Fund Name, Category, Risk, NAV, Expense Ratio, ...
Fund Name: HDFC Mid Cap Fund | Category: Equity | Risk: Very High | NAV: 219.44 | Expense Ratio: 0.76 | ... | Exit Load: Exit load of 1% if redeemed within 1 year
```

Tables are processed first and then decomposed, so their cells are not also dumped as unlabelled text. A non-numeric-looking first row is treated as the header; ragged rows (some funds have no exit-load cell) are handled by position. Chunk count rose 47 → 84 because labelled rows are longer than bare values.

### Fix 2 — Row-aware hybrid re-ranking (`src/retrieval/retriever.py`)

Dense candidates are pulled from ChromaDB, then re-scored:

- `_segments()` splits table chunks on the `Fund Name:` marker so each fund row is scored independently — a chunk scores as well as its *best-matching row*, which is what finally separates "Expense Ratio: 0.77" (Flexi Cap) from the Small Cap row.
- `_segment_score()` combines query-term overlap, exact domain phrase hits (`expense ratio`, `exit load`, `lock-in`, `riskometer`, ...), and a scheme-name check.
- `_terms()` splits glued names, so "hdfc flexicap" matches "HDFC Flexi Cap".
- `_norm()` makes the scheme check spacing-insensitive and distinguishes **Large Cap** from **Large & Mid Cap**: the hint must appear as one name, otherwise the words-only match is penalised.
- `CANDIDATE_POOL=0` re-ranks every chunk in the collection. With ~84 chunks this is cheap and removes the "dense lottery" that dropped the correct row before re-ranking.
- The scheme bonus is now applied per chunk *and* skipped for table chunks that name a different fund, so the AMC row is no longer pushed below the scheme's own page.

### Fix 3 — Testing through the real retriever

`run_ingest.py --step query` called ChromaDB directly, so it showed raw cosine results and none of the retriever's logic — earlier "failures" were measured on the wrong path. It now calls `retrieve()`.

### Supporting fixes

- `vector_store.get_collection()` drops the collection via the ChromaDB API instead of `shutil.rmtree`; deleting the folder fails on Windows while the client holds `chroma.sqlite3` open (`WinError 32`).
- `SCHEME_KEYWORDS` is ordered longest-first so "large & mid cap" wins over "large cap".

**Verification:** index rebuilds to 84 records; "expense ratio of HDFC Flexi Cap" → 0.77%, "expense ratio of HDFC Mid Cap Fund" → 0.76%, "exit load of HDFC Mid Cap Fund" → 1% if redeemed within 1 year. `sample_qa.md` regenerated.

**Still unanswerable (not a bug):** HDFC Large Cap Fund has no row in the AMC table, so its expense ratio is absent; ELSS lock-in, riskometer/benchmark and statement-download text lives on `hdfcmf.com`, which is unreachable (see `data/sources.md`).

---

## Phase 10 — Deployment (added after the Render outage)

The app deployed successfully but the site was unreachable: the build finished, then every request returned a 502 or timed out. Retrying the build did not help.

**Diagnosis.** Measured RSS stage by stage with `psutil` while a real question was answered:

| Stage | RSS |
|---|---|
| Bare Python | 17 MB |
| `import torch` | 194 MB |
| Embedding model loaded | 534 MB |
| ChromaDB index loaded | 672 MB |
| Streamlit imported | **680 MB** |
| Render free tier limit | **512 MB** |

Over budget by 168 MB, so Linux OOM-killed the container on every start. It was briefly reachable only in the window between booting and being killed, which is why it looked intermittent rather than broken.

**Root cause.** Not the model. `all-MiniLM-L6-v2` is 90 MB of weights; PyTorch costs 194 MB just to import and another 340 MB to hold them, because it reserves large arenas and does not return them.

**Fix — same weights, lighter runtime.** `src/ingestion/embedder.py` now runs the exported graph (`onnx/model.onnx`, 86 MB) through ONNX Runtime with Rust `tokenizers`, doing mean pooling over the attention mask and L2 normalisation to match `1_Pooling/config.json`.

| Stage | ONNX |
|---|---|
| Bare Python | 17 MB |
| Model loaded | 178 MB |
| After retrieval | 218 MB |
| After answering a question | **235 MB** |

`EMBEDDER_BACKEND` selects `onnx` (default) or `torch`; if `onnxruntime` cannot load, the module falls back to `sentence-transformers` automatically, so no environment ends up without embeddings.

**Verification.** `src/ingestion/test_embedder_backends.py` embeds five probes through both backends in separate subprocesses and compares them: **cosine similarity 1.000000** on every probe. Full suite re-run on the ONNX-built index — guardrails 11/11, coverage sweep 13/15 (the same two pre-existing misses), Groq answers unchanged. Live deployment verified with 12/12 successful requests, median 0.38s, against 5/6 timeouts at 90s beforehand.

**Also in this phase**
- `ensure_index()` in `src/app.py` builds the vector index whenever `chroma_db/` is missing, wrapped in `st.cache_resource`. `chroma_db/` is git-ignored, so previously every host needed a separate ingestion build step; now a fresh clone or cloud deploy is self-sufficient. Verified from a genuinely empty index: 84 chunks from 6 pages in 8.6s, second call a no-op.
- `render.yaml` makes build command, start command, health check path and required env vars declarative, so a mistyped module name cannot break a build again.
- `.streamlit/config.toml` tracked for theming, with `secrets.toml` still ignored.

---

## Phase Order & Dependencies

```
Phase 0 → 1 → 2 → 3 → 5 → 6 → 7 → 8 → 9 → 10
                 └→ 4 (guardrails) can be done any time before 6
```

## Definition of Done (whole project)

- [ ] Every factual answer has exactly one corpus citation link.
- [ ] Advice/portfolio queries are refused with an educational link.
- [ ] No computed/compared returns anywhere.
- [ ] "Last updated from sources:" appears on every answer.
- [ ] UI shows the facts-only disclaimer.
- [ ] No PII fields or storage.
- [x] Public demo link reachable on a free-tier host (<https://rag-chatbot-yr9e.onrender.com>).
- [x] Peak RSS 235 MB, inside the 512 MB free-tier budget.
- [x] No API keys committed; `.env` and `secrets.toml` git-ignored.

**Known retrieval gaps** (facts exist in the corpus but rank outside the top 4, so the bot declines rather than guessing): "fund size / AUM of HDFC Mid Cap Fund", "who manages HDFC Mid Cap Fund".
