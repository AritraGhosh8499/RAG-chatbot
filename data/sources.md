# Sources

## Ingested corpus (6 pages)

| # | Type | Scheme | URL | Status |
|---|---|---|---|---|
| 1 | AMC overview | HDFC Mutual Funds | https://groww.in/mutual-funds/amc/hdfc-mutual-funds | OK |
| 2 | Large cap | HDFC Large Cap Fund (Direct, Growth) | https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth | OK |
| 3 | Flexi cap | HDFC Equity Fund (Direct, Growth) | https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth | OK |
| 4 | ELSS | HDFC ELSS Tax Saver Fund (Direct, Growth) | https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth | OK |
| 5 | Mid cap | HDFC Mid Cap Fund (Direct, Growth) | https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth | OK |
| 6 | Regulator / investor education | AMFI Investor Corner | https://www.amfiindia.com/investor | OK |

## Official sources we wanted but could not ingest

These were attempted during Phase 3/5 and are recorded here so the gap is explicit rather than silent.

| Intended fact | Intended URL | Result |
|---|---|---|
| Scheme-wise expense ratio, exit load schedule | https://www.hdfcmf.com/ | Connect timeout — host unreachable from the demo network |
| Factsheets (expense ratio, benchmark, riskometer) | https://www.hdfcmf.com/ (factsheet PDFs) | Same — unreachable |
| Statement / tax-doc download guide | https://mfutility.in/ | Connection error — unreachable |
| ELSS lock-in, riskometer education | https://www.hdfcaml.com/ , https://www.amfiindia.com/investor/* | DNS failure / 404 (AMFI sub-pages are client-rendered) |

**Consequence:** questions about ELSS lock-in period, riskometer rating/benchmark, and how to download a capital-gains statement have **no supporting text in the corpus**. The assistant must answer "not available in my sources" and link an official page rather than guess.

**Actionable:** re-run ingestion from a network that can reach `hdfcmf.com` (e.g. a different ISP/VPN) and add these URLs to `CORPUS` in `src/ingestion/loader.py`; no other code change is needed.

## Fact coverage in the current corpus

Derived from the 6 ingested pages after the Phase 9 retrieval fixes. "Covered" means the fact exists in the indexed text and is retrievable.

| Fact | Covered | Where it comes from |
|---|---|---|
| Expense ratio | Yes, for schemes listed in the AMC table (Mid Cap 0.76, Flexi Cap 0.77, Large & Mid Cap 0.92, ...) | AMC overview table |
| NAV | Yes, for the same schemes | AMC overview table |
| Exit load | Yes | Scheme pages + AMC table |
| Minimum SIP / lump sum | Yes | AMC overview page |
| Fund management company | Yes | AMC overview + scheme pages |
| **Expense ratio of HDFC Large Cap Fund** | **No** | No plain "Large Cap" row exists in the AMC table, and the Large Cap page does not publish the ratio. The "Large & Mid Cap" value is deliberately *not* substituted. |
| ELSS lock-in period | No | Would require `hdfcmf.com` (unreachable) |
| Riskometer rating / benchmark | No | Would require HDFC factsheet PDFs (unreachable) |
| Capital-gains statement download | No | Would require `mfutility.in` (unreachable) |
