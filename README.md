# AuditFlow AI

An evidence-driven financial audit application with a React dashboard, Flask API, SQLAlchemy persistence, FAISS hybrid retrieval, deterministic financial checks, Isolation Forest anomaly indicators and an eight-stage LangGraph workflow. Financial calculations use `Decimal`; material decisions require an independent human reviewer.

Hosted synthetic demo: **https://auditflow-ai-five.vercel.app**. This Vercel deployment uses a dedicated Neon PostgreSQL database and stores originals durably in database-backed evidence storage. See `docs/vercel.md` for hosting limits and configuration.

## Quick start (Python 3.12 recommended, Node 22+)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt
cd backend
python -m flask --app run init-db
python -m flask --app run seed-demo
python run.py
```

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open **http://127.0.0.1:5173**. To serve everything through Flask instead, run `npm run build` inside `frontend`, then open **http://127.0.0.1:5000**. On macOS/Linux use `source .venv/bin/activate` and `python` instead of the Windows executable path. This workspace also has a tested `.venv312` using the bundled Python 3.12 runtime.

With dependencies and the frontend build present, Windows users can run `./start-auditflow.ps1 -SeedDemo` from the repository root. The script starts the local application in the current terminal; Ctrl+C stops it.

Local startup defaults to SQLite at `data/auditflow.db` and a generated per-process JWT secret. Set a persistent `SECRET_KEY` in the root `.env` to preserve sessions across restarts. For local SQLite, leave `DATABASE_URL` unset. `.env.example` contains the PostgreSQL container URL; do not copy that URL into a local SQLite setup.

## Synthetic demo accounts

| Role | Email | Password |
| --- | --- | --- |
| Auditor | auditor@auditflow.demo | AuditFlowDemo!2026 |
| Reviewer | reviewer@auditflow.demo | AuditFlowDemo!2026 |
| Administrator | admin@auditflow.demo | AuditFlowDemo!2026 |

Seed data is explicitly synthetic. It includes duplicate invoices, a missing vendor, a tax arithmetic mismatch, an unbalanced journal, an unusual amount and a bank/cash-book mismatch of INR 5,000. No external emails or messages are sent. Do not enable demo seeding for a real engagement.

## Demonstration workflow

1. Sign in as auditor; create a project or open the synthetic audit.
2. Upload the CSV files in `data/sample`, choosing their document categories. Uploading indexes source text automatically.
3. Inspect a document to see its hash, version, extraction method, original download and extracted source locations.
4. Ask the assistant `Find purchase invoice INV-001`. Follow a citation to the source viewer.
5. Map requirements, then run verification/reconciliation individually or run the full agent workflow.
6. Inspect the INR 5,000 discrepancy, duplicate invoice and incomplete evidence. Add a documented observation or comment.
7. Log out and sign in as the assigned reviewer. Review each finding. Review supporting sources and confirm requirement adequacy.
8. Missing categories must be supplied before they can be mapped and reviewed. Do not approve a synthetic audit with missing evidence merely to complete a demonstration.
9. Approve the audit after reviewing all requirements and findings. Generate PDF/Excel reports. Earlier snapshots remain marked draft.

## Data import

CSV and XLSX use headers, automatically normalized by case and spaces. Recognized fields include `reference,date,invoice_number,vendor,customer,amount,currency,net,tax,total,debit,credit,account_code,opening_balance,closing_balance,employee_id,salary,deductions`. `Invoice No`, `Total Amount` and other aliases are recognized; unknown columns are retained. Monetary values support 4 decimal places, dates use ISO `YYYY-MM-DD`, currencies must be supplied. Each imported row retains worksheet/row provenance. Invalid monetary values fail the document visibly rather than being coerced to zero. PDF/DOCX/image text is searchable, but unstructured text is not silently turned into financial transaction rows.

## Docker and PostgreSQL

Create a root `.env` with a random `SECRET_KEY` of at least 32 characters, `POSTGRES_PASSWORD`, and `DEMO_MODE=true` for the demonstration. Then:

```sh
docker compose build
docker compose up -d db
docker compose run --rm backend python -m flask --app run init-db
docker compose run --rm backend python -m flask --app run seed-demo
docker compose up -d
```

Open **http://127.0.0.1:8080**. Tesseract is included in the backend image. Database and originals use persistent volumes. Use `DEMO_MODE=false` for real data; provision users with the administrative CLI rather than the demo seed. Docker execution requires Docker Desktop; its availability is separate from local tests.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q --basetemp .test-tmp
cd frontend
npm test
npm run build
```

Tests cover login/logout, registration privilege boundaries, project isolation, immutable source versions, citations, invalid archives, extraction failures, real PDF/DOCX/XLSX parsers, the OCR adapter, exact decimal reconciliation, currency/date boundaries, deterministic anomaly detection, LangGraph, draft exports and independent approval. The OCR adapter unit test substitutes OCR output; an actual Tesseract executable is required for real OCR testing. Live paid LLM calls and Docker/PostgreSQL need their respective credentials/runtime and are not implied by local test results.

See `docs/validation.md` for the exact validation scope. The assistant also routes supported duplicate, amount-threshold, discrepancy and incomplete-requirement questions to deterministic backend tools with source references. New evidence or matching-rule changes invalidate current check results and require a new run.

## Optional LLM quote selection

Set `ANTHROPIC_API_KEY` and `LLM_MODEL` to an available model identifier. Only relevant retrieved passages and the question are sent to the provider. The model can select source quotes, not issue audit conclusions or invoke tools. Pydantic validates JSON and every quote must be an exact substring of a cited source. Invalid output/network errors fall back to local retrieval with a visible warning. No key is needed for the complete local workflow. Provider integration follows the [Messages API contract](https://platform.claude.com/docs/en/api/overview).

## Important implementation boundaries

- The default embedding is a deterministic 512-dimensional token hash, **not a learned semantic embedding**. FAISS exact inner-product search is combined with keyword overlap. For learned semantic embeddings, install `backend/requirements-semantic.txt`, set `EMBEDDING_MODEL` to an existing local model directory/cached model ID, and reindex every active document. Model downloading is disabled unless `ALLOW_MODEL_DOWNLOAD=true`; remote model code is always disabled. This adapter follows the [Sentence Transformers API](https://sbert.net/docs/package_reference/sentence_transformer/model.html). Its interface is unit-tested, but model weights were not downloaded or benchmarked locally. See the [FAISS index reference](https://github.com/facebookresearch/faiss/wiki/Faiss-indexes).
- LangGraph runs actual backend functions against project records; model-controlled agents are not used to calculate financial results. The workflow follows the [StateGraph API](https://reference.langchain.com/python/langgraph/graph/state).
- Processing is synchronous and bounded. Agent completion budgets detect overruns after a call returns; they do not forcibly terminate Python work. A durable job queue, distributed limiter and hard cancellation are required for large production deployments.
- Matching is one-to-one with tolerance/date/reference controls. Ambiguous matches are flagged. Many-to-one partial settlement allocation is not implemented.
- Current-results tables are refreshed on runs; reports and execution logs preserve earlier snapshots. Reviewer decisions on generated findings are retained; findings are not automatically resolved on later runs.
- Database migrations include a versioned initial migration, not an unrestricted automatic schema upgrade system.
- No regulatory assurance, authenticity determination, fraud conclusion, automatic financial record modification or autonomous final audit opinion is produced.

See `docs/architecture.md`, `docs/api_documentation.md`, `docs/database_schema.md`, `docs/rag_pipeline.md`, `docs/agent_workflow.md`, `docs/methodology.md`, `docs/user_manual.md` and `docs/deployment.md` for design and operating details.
