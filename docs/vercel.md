# Vercel deployment

Production URL: **https://auditflow-ai-five.vercel.app**. Hosted smoke checks passed for login, original download, cited retrieval, LangGraph execution and PDF export. The associated dedicated Neon database contains the synthetic audit and five durable original evidence files.

The root Vercel project serves the Vite build and routes `/api/*` to `api/index.py`. Flask uses a managed PostgreSQL database (`DATABASE_URL`) and a persistent session secret (`SECRET_KEY`). Set those as project environment variables. Never expose either to Vite/client code. Python 3.12 is declared in `.python-version`.

Original files are stored as immutable binary rows in `document_blobs` on hosted deployments. `/tmp/auditflow` is only a processing cache. Download and reindex operations can recover originals when the local cache is gone; SHA-256 is checked before reindexing. Migration 2 creates this storage table. Cold-start schema/sample initialization is serialized with a PostgreSQL advisory lock.

The deployed demonstration uses synthetic records and public demo accounts. Do not upload confidential evidence to this demonstration. Root `.vercelignore` excludes all local databases, upload directories, Python environments, credentials and QA outputs; only the synthetic sample input files are packaged.

Vercel request-body limits require smaller uploads than the local application: 3 MB per file and 4 MB total request on this deployment. Large uploads and actual Tesseract OCR require separate worker/storage infrastructure. Vercel has no bundled Tesseract executable; unsupported OCR attempts remain explicit extraction failures. Local hashing, FAISS retrieval, rules, reconciliation, anomaly indicators, LangGraph, review and report generation use the hosted Python API.

Provisioning used a new free Neon resource dedicated to AuditFlow. PostgreSQL records and originals persist between serverless cold starts. No unrelated project or database is used. Keep a backup/retention policy before any production use; this is the synthetic demonstration deployment.

Deploy changes from the root with `vercel deploy --prod`. Avoid committing `.env.local`, `.env.production.local`, or `.vercel` credentials/state.
