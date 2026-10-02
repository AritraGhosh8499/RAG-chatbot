# PRD — MF Scheme FAQ RAG Chatbot (Class Demo)

## 1. Overview
A small Retrieval-Augmented Generation (RAG) FAQ assistant that answers factual questions about HDFC mutual fund schemes, grounded only in official public pages provided in the project corpus. Every answer must cite one source link, stay factual, and avoid investment advice.

## 2. Problem Statement
Retail users and support/content teams repeatedly ask the same factual questions about mutual fund schemes — expense ratio, exit load, minimum SIP, lock-in (ELSS), riskometer, benchmark, and how to download statements. Answers must come from verifiable public sources, not guesswork.

## 3. Goals
- Answer factual queries about one AMC (HDFC) and its schemes using only a fixed corpus of public pages.
- Provide exactly one clear citation link per answer.
- Refuse opinionated / portfolio questions ("Should I buy/sell?") politely, with a relevant educational link.
- Never compute or compare returns; link to the official factsheet when asked.
- No PII collection or storage (no PAN, Aadhaar, account numbers, OTPs, emails, phone numbers).

## 4. Non-Goals
- Personalized investment advice, portfolio recommendations, or return projections.
- Ingesting arbitrary websites, third-party blogs, or user screenshots.
- User accounts, persistence of chat history with PII, or email capture.

## 5. Scope
- **AMC:** HDFC Mutual Funds
- **Schemes (corpus):** 4 schemes covering large cap, flexi cap, ELSS, mid cap — plus the AMC overview page. All pages sourced from Groww's public pages (as provided in the milestone brief).
- **Demo context:** class demo, not a production service.

### Corpus URLs
| Type | URL |
|---|---|
| AMC overview | https://groww.in/mutual-funds/amc/hdfc-mutual-funds |
| Large cap | https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth |
| Flexi cap | https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth |
| ELSS | https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth |
| Mid cap | https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth |

## 6. Users & Use Cases
- **Retail user comparing schemes:** "What is the expense ratio of HDFC Large Cap Fund (Direct, Growth)?"
- **Retail user:** "What is the ELSS lock-in period?", "What is the minimum SIP?", "What is the exit load?", "What is the riskometer/benchmark?"
- **Support/content team:** "How do I download a capital-gains statement?"

## 7. Functional Requirements

### 7.1 RAG Pipeline (two stages, both fully demonstrated)
**Stage 1 — Data Ingestion (offline):**
1. **Loading:** Fetch the 5 URLs above and extract text content.
2. **Chunking:** Chunk the extracted text (strategy chosen based on the nature of the page content — variable-size, respecting semantic boundaries like headings/paragraphs).
3. **Embedding:** Generate embeddings with `sentence-transformers/all-MiniLM-L6-v2`.
4. **Vector store:** Persist embeddings + metadata (source URL, scheme, chunk id) in **ChromaDB**.

**Stage 2 — Data Retrieval & Generation (online):**
1. Embed the user query with the same embedding model.
2. Retrieve top-k relevant chunks from ChromaDB.
3. Build a prompt with retrieved chunks as context.
4. LLM generates an answer constrained to the context.
5. Return the answer with one source link (the URL of the most relevant chunk).

### 7.2 Answering Rules
- Factual queries only; unknown answers → say so and give the closest relevant source link.
- Answers ≤ 3 sentences, followed by "Last updated from sources: <date>".
- Every answer includes exactly one citation link from the corpus.
- Portfolio/advice questions → polite refusal with an educational link.

### 7.3 UI (tiny)
- Welcome line, 3 example questions, and the note: **"Facts-only. No investment advice."**
- Chat input + answer area showing answer text, citation link, and the "Last updated from sources:" line.

## 8. Non-Functional Requirements / Constraints
- Public sources only; no third-party blogs; no screenshots of the back-end in deliverables.
- No PII acceptance or storage.
- No performance claims; no computed or compared returns.
- Clarity & transparency: short answers, visible source, visible last-updated note.

## 9. Tech Stack
| Component | Choice |
|---|---|
| Embedding model | sentence-transformers/all-MiniLM-L6-v2 |
| Vector DB | ChromaDB |
| Chunking | Chosen per data content (semantic/paragraph-aware) |
| Loader | HTTP-based fetch + text extraction |
| LLM | TBD (OpenAI / other chat model) for generation |
| UI | Simple web UI (Streamlit/Gradio) or notebook |

## 10. Deliverables
1. Working prototype (hosted app/notebook) or ≤3-min demo video.
2. Source list (CSV/MD) of the 5 URLs.
3. README: setup steps, scope (AMC + schemes), known limits.
4. Sample Q&A file: 5–10 queries with answers + links.
5. Disclaimer snippet used in the UI.

## 11. Sample Queries
- "Expense ratio of HDFC Mid Cap Fund (Direct, Growth)?"
- "What is the ELSS lock-in period?"
- "Minimum SIP for HDFC Flexi Cap (Direct, Growth)?"
- "Exit load for HDFC Large Cap Fund?"
- "What is the riskometer rating and benchmark?"
- "How to download a capital-gains statement?"
- "Should I buy HDFC ELSS now?" → must refuse.

## 12. Success Metrics (demo)
- 100% of in-scope factual answers include exactly one valid corpus citation.
- 0 advice/opinionated answers; refusals include an educational link.
- Retrieval returns relevant chunks for the sample queries above.

## 13. Risks & Known Limits
- Groww pages may change; corpus needs re-ingestion (note "Last updated from sources").
- Chunking/embedding mismatch can surface irrelevant chunks — tune top-k and chunk size.
- Small corpus limits coverage; unanswered queries must degrade gracefully.
- No real-time NAV/performance data; direct users to official factsheet.

## 14. Out of Scope (explicit)
Multi-AMC support, live NAV lookup, personalized advice, returns comparison, user accounts, PII, production deployment, streaming answers.
