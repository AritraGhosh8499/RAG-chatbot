# Architecture — MF Scheme FAQ RAG Chatbot

## 1. High-Level Overview

The system is a classic two-stage RAG pipeline: an **offline ingestion pipeline** that builds a searchable vector index from 6 public pages, and an **online retrieval + generation pipeline** that answers user queries grounded in that index.

```
                        ┌──────────────────────────────────────────────┐
                        │              OFFLINE (Stage 1)               │
                        │                                              │
  5 public pages ──▶  Loading ──▶ Chunking ──▶ Embedding ──▶ Vector DB │
  (Groww/HDFC)                                              (ChromaDB) │
                        └──────────────────┬───────────────────────────┘
                                           │ indexed chunks + metadata
                        ┌──────────────────▼───────────────────────────┐
                        │             ONLINE (Stage 2)                 │
                        │                                              │
  User query ──▶ Query embedding ──▶ Top-k retrieval ──▶ Prompt build  │
                                           │                          │
                                           ▼                          │
                              LLM generation ──▶ Answer + 1 citation  │
                        └──────────────────────────────────────────────┘
```

## 2. Component Diagram

```
┌──────────┐   query   ┌─────────────┐
│  User    │ ────────▶ │  Chat UI    │
└──────────┘           │ (Streamlit/ │
     ▲                │  Gradio)    │
     │ answer + link  └──────┬──────┘
     │                       │
     │                ┌──────▼──────┐      ┌────────────────┐
     │                │ Orchestrator│─────▶│ Safety/        │
     │                │ (guardrails)│◀─────│ Advice filter  │
     │                └──────┬──────┘      └────────────────┘
     │                       │
     │                ┌──────▼──────┐      ┌────────────────┐
     │                │  Retriever  │─────▶│ ChromaDB       │
     │                │ (embed query│      │ (vectors +     │
     │                │  top-k)     │◀─────│  metadata)     │
     │                └──────┬──────┘      └────────────────┘
     │                       │ context chunks
     │                ┌──────▼──────┐
     │                │ LLM         │
     │                │ (answer gen │
     └────────────────│ + citation) │
                      └─────────────┘
```

## 3. Stage 1 — Data Ingestion (Offline)

| Step | Component | Detail |
|---|---|---|
| 1. Loading | `loader.py` | HTTP fetch of the 6 corpus URLs; strip boilerplate (nav, footer, scripts); keep headings + paragraphs. HTML **tables are rendered as labelled key-value rows** (`Fund Name: HDFC Mid Cap Fund | Expense Ratio: 0.76 | ...`) instead of a flat cell dump, so each fact keeps its column meaning. |
| 2. Chunking | `chunker.py` | Semantic/paragraph-aware chunking — split on headings and paragraphs, merge small segments, cap chunk size (e.g., ~500–800 chars) with small overlap. Strategy chosen based on page structure. |
| 3. Embedding | `embedder.py` | `sentence-transformers/all-MiniLM-L6-v2` — same model must be used at retrieval time. |
| 4. Vector store | `vector_store.py` | ChromaDB persistent collection. Each record stores: embedding vector, chunk text, and metadata `{source_url, scheme_name, chunk_id}`. |

Output: a local ChromaDB directory (e.g., `./chroma_db`) + a `sources.csv/md` manifest.

## 4. Stage 2 — Retrieval & Generation (Online)

1. **Guardrail check** — classify the incoming query:
   - Advice/portfolio question ("Should I buy/sell?", "Which fund is best for me?") → polite refusal + educational link. No retrieval/LLM call needed.
   - Otherwise → continue.
2. **Query embedding** — embed the user's question with `all-MiniLM-L6-v2`.
3. **Hybrid retrieval** — ChromaDB cosine similarity gives a broad candidate set, then a lexical re-rank decides the final top-k:
   - **Why:** every row of the AMC fund table embeds almost identically, so dense similarity cannot separate "Expense Ratio: 0.77 (Flexi Cap)" from the Small Cap row.
   - **Row-aware scoring:** table chunks are split on the `Fund Name:` marker and each row is scored separately; a chunk scores as well as its *best-matching row*.
   - **Signals:** query-term overlap, exact domain phrases ("expense ratio", "exit load"), and a scheme-name match that ignores spacing ("hdfc flexicap" ≈ "HDFC Flexi Cap"), with a penalty when the scheme words appear in the wrong order/name ("Large Cap" vs "Large & Mid Cap").
   - **Relevance gate:** if the best final score is below `MIN_SCORE`, return nothing and answer "not in my sources" instead of forcing a weak match.
4. **Prompt construction** — system prompt enforcing: facts-only, ≤3 sentences, no returns computation, one citation, add "Last updated from sources:". Context = retrieved chunks.
5. **Generation** — LLM produces the answer grounded in the context (Groq by default; extractive quoting if no key or the API fails).
6. **Post-processing** — attach exactly one citation link (the `source_url` of the top-ranked chunk), append "Last updated from sources: <date>", and return to the UI.

## 5. Data Flow Summary

```
URL ─▶ raw text ─▶ chunks ─▶ embeddings ─▶ ChromaDB
                                              │
query ─▶ embedding ─▶ top-k chunks ─▶ prompt+context ─▶ LLM ─▶ answer+citation
```

## 6. Metadata Schema (ChromaDB record)

```json
{
  "id": "hdfc-large-cap_chunk_07",
  "document": "<chunk text>",
  "embedding": [0.012, ...],
  "metadata": {
    "source_url": "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
    "scheme": "HDFC Large Cap Fund (Direct, Growth)",
    "amc": "HDFC",
    "chunk_id": 7
  }
}
```

## 7. Suggested Project Structure

```
├── docs/
│   ├── PRD.md
│   ├── architecture.md
│   └── problemstatement.txt
├── data/
│   └── sources.md
├── src/
│   ├── ingestion/
│   │   ├── loader.py
│   │   ├── chunker.py
│   │   ├── embedder.py
│   │   └── vector_store.py
│   ├── retrieval/
│   │   ├── retriever.py
│   │   └── prompts.py
│   ├── guardrails.py        # advice-refusal filter
│   └── app.py               # Streamlit/Gradio UI
├── chroma_db/               # persisted vector store
├── notebooks/               # demo notebook (optional)
├── sample_qa.md             # sample Q&A deliverable
├── README.md
└── requirements.txt
```

## 8. Key Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Embedding model | all-MiniLM-L6-v2 | Lightweight, fast on CPU, good for demo; reused at query time. |
| Vector DB | ChromaDB | Zero-config, local persistence, built-in metadata filtering. |
| Chunking | Paragraph/heading-aware | MF pages vary in structure; semantic boundaries preserve facts (e.g., expense ratio tables). |
| Table handling | Rows rendered as labelled `Column: value` text | A flat cell dump ("2,150.08 0.77") is unretrievable; labelled rows make every fact self-describing. |
| Retrieval ranking | Hybrid: dense candidates + row-aware lexical re-rank | Dense embeddings alone cannot distinguish near-identical table rows; the lexical pass makes exact-phrase questions ("expense ratio") land on the right row. |
| Citation strategy | Top-chunk `source_url` | Guarantees one verifiable link per answer, consistent with constraints. |
| Guardrails-first | Filter before retrieval | Prevents advice leakage and wasted LLM calls. |
| Facts-only prompt | System-level instruction | Enforces ≤3 sentences, no returns, no PII, last-updated line. |
| LLM provider | Groq (`openai/gpt-oss-120b`), extractive fallback | Keeps embeddings/retrieval local; app still answers (by quoting) with no API key. |

## 9. Constraints Mapped to Architecture

- **Public sources only** → loader restricted to the 6 URLs; no arbitrary web search.
- **No PII** → UI/prompt forbids requesting identifiers; nothing is persisted except embeddings of public text.
- **No performance claims** → prompt explicitly bans computed/compared returns.
- **Clarity & transparency** → answer template enforces ≤3 sentences + citation + "Last updated from sources:".
