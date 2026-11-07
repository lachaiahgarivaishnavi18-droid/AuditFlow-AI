# AuditFlow AI architecture and implementation contract

React/Vite communicates with a same-origin Flask REST API. SQLAlchemy persists users, organizations, projects, immutable original document versions, chunks, extracted records, requirements, mappings, checks, reconciliations, findings, comments, requests, notifications, report snapshots and execution/audit logs. PostgreSQL is the deployment database; SQLite is the local demonstration adapter.

## Trust boundaries
Bearer JWTs carry a session identifier and expiry; logout revokes sessions. Registration can create auditors only. Administrators manage roles. Project access is restricted to the assigned auditor, assigned reviewer and administrators. Reviewer approval cannot be performed by the assigned auditor. Uploads are untrusted data, stored under generated names outside the web root. Downloads, retrieval, exports and all mutations recheck project authorization.

## Document and RAG pipeline
Validate extension, parser and size -> hash -> store immutable original -> extract page/worksheet units -> parse financial rows -> overlapping chunks -> FAISS vector and keyword hybrid retrieval. Each hit retains document/version/page/worksheet and source text. Default local hashing responses are extractive. An optional Sentence Transformers adapter supports explicitly configured local model weights; model changes require reindexing. An optional external LLM selects exact validated source quotes only. Failed extraction remains visible and workflow stops for remediation.

## Agent workflow
LangGraph typed shared state: collection -> intelligence -> retrieval -> requirement mapping -> deterministic verification/reconciliation -> anomaly detection -> analysis -> reporting -> human review checkpoint. Pydantic validates node outputs. Bounded retries and elapsed-time limits apply to each node. Outputs and model/prompt versions are logged. Missing requirements create internal evidence requests. A persisted workflow run awaits reviewer action before finalization. Re-running replaces generated current results, preserving immutable execution snapshots in logs and reports.

## API contracts
All authenticated endpoints require Authorization: Bearer JWT. Responses are JSON objects or arrays; errors are {error, code}. Lists accept page/per_page and return {items,total,page,per_page}. All financial values serialize as decimal strings. POST uploads use multipart files, audit_id, category; other POST/PUT requests use JSON. API endpoints and generated schema are in /api/contracts and docs/api_documentation.md.

## Financial checks
Rules operate on normalized CSV/XLSX rows with source references and Decimal values. Unstructured text yields extracted fields only, never fabricated transactions. Schema: reference,date,amount,currency,invoice_number,vendor,debit,credit,opening_balance,closing_balance,tax,net,total,employee_id,salary,deductions,account_code. Missing fields produce Incomplete/Not Verifiable. Matching uses reference, currency, date window, one-to-one consumption, and configurable amount tolerance. Different currencies are never aggregated or reconciled. Anomaly indicators are investigatory only. Passing checks establish only the stated consistency condition.

## Deployment and limitations
Synchronous bounded demonstration processing; no production task queue. Tesseract must be installed for OCR. Antivirus can be configured through a fixed executable path; absent scanning is explicitly recorded. TLS, backups, production secret and operational hardening are deployment responsibilities. No external messages are sent. No autonomous audit opinions. No LLM integration is claimed in local mode.
