# Database schema

SQLAlchemy models in `backend/app/models.py` are the authoritative schema, supporting PostgreSQL and the SQLite demonstration adapter. Run `flask --app run init-db` to apply version 1, tracked in `schema_migrations`. Startup never drops tables. Monetary fields use `NUMERIC(24,4)` on PostgreSQL and exact decimal strings on SQLite; financial row values and source-original amounts are stored as decimal strings in JSON.

| Table | Purpose and relationships |
| --- | --- |
| users | Unique email, hashed password, role |
| sessions | Unique JWT token ID, user FK, revocation |
| organizations | Organization identity |
| audit_projects | Organization, assigned auditor and reviewer FKs; dates/status/configuration |
| documents | Audit/uploader FKs, SHA-256, immutable file reference, version and prior-version FK; unique audit/name/version |
| document_blobs | Unique document FK and immutable binary original for hosted persistence; migration 2 |
| document_chunks | Document FK, text/page/section and persisted vector |
| financial_records | Document FK, original normalized values and exact source row |
| audit_requirements | Audit FK, expected categories, reviewed completeness |
| evidence_mappings | Requirement and document FKs, source location and category match score |
| verification_results | Audit/source/comparison FKs, decimal compared values, precise rule explanation |
| reconciliation_records | Audit FK, source references, decimal differences, currency/status |
| audit_findings | Audit/reviewer FKs, evidence refs, human review decisions |
| agent_logs | Audit FK, run ID, validated outputs, version/timing/errors |
| analyst_comments | Audit/finding/user FKs, dated review history |
| audit_logs | User FK, action/resource/details and timestamp |
| evidence_requests | Audit/requirement FKs, requested category and fulfillment |
| notifications | User/audit FKs, message/read state |
| reports | Audit/reviewer FKs, format, immutable JSON snapshot |
| retrieval_history | Audit/user FKs, question and cited response |

Indexes exist on audit-scoped records, document chunk/row references, hash, user-scoped resources and execution run IDs. Originals and historical report snapshots are retained. Physical deletion is intentionally not exposed through the application API.
