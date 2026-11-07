# REST API contract

API base: `/api`. JSON requests use `Content-Type: application/json`. Authentication uses `Authorization: Bearer <JWT>`. Sessions expire after eight hours and logout revokes the session. Public registration always creates auditors. Errors are `{ "error": "message", "code": 400 }`; Pydantic validation also returns field details. List endpoints accept `page` and `per_page` (maximum 100), returning `{items,total,page,per_page}`. Financial values serialize as decimal strings.

`GET /api/contracts` returns the exact registered route/method inventory.

| Area | Endpoints | Request |
| --- | --- | --- |
| Auth | POST `/auth/register`, POST `/auth/login`, POST `/auth/logout`, GET `/auth/me` | register: username,email,password; login: email,password |
| Projects | GET/POST `/audits`, GET/PUT/DELETE `/audits/{id}` | create: project_name,organization_name,financial_year,audit_period_start,audit_period_end,audit_type,reviewer_id; delete archives project |
| Approval | POST `/audits/{id}/approve` | comment; assigned independent reviewer only; all requirements and findings reviewed |
| Documents | POST `/documents/upload`, POST `/documents/bulk-upload`, GET `/documents`, GET `/documents/{id}`, GET `/documents/{id}/status`, GET `/documents/{id}/extracted-text`, GET `/documents/{id}/download`, DELETE `/documents/{id}` | multipart: files (repeatable),audit_id,category,description; delete archives |
| Retrieval | POST `/rag/query`, POST `/rag/index/{document_id}`, POST `/rag/reindex/{audit_id}`, GET `/rag/retrieval-history/{audit_id}` | query: audit_id,query,top_k (1-20),category?,document_id? |
| Evidence | GET `/evidence/{id}`, GET `/evidence/missing/{id}`, GET `/evidence/coverage/{id}`, POST `/evidence/map` | map: audit_id; GETs return requirements,mappings,requests,complete,total |
| Requirements | POST `/requirements`, POST `/requirements/{id}/review` | create: audit_id,requirement_name,required_evidence_type (category array); review: approve,comment |
| Verification | POST `/verification/run/{audit_id}`, GET `/verification/results/{audit_id}`, GET `/verification/{id}` | run: no body |
| Reconciliation | POST `/reconciliation/run/{audit_id}`, GET `/reconciliation/results/{audit_id}` | run: no body |
| Anomalies | GET `/anomalies/{audit_id}` | returns indicators, method, sample_count |
| Agents | POST `/agents/run/{audit_id}`, GET `/agents/status/{audit_id}`, GET `/agents/logs/{audit_id}` | run returns run_id,failed,awaiting_review,output; GETs return persisted logs |
| Findings | GET `/findings/{audit_id}`, POST `/findings`, PUT `/findings/{id}`, POST `/findings/{id}/review`, GET `/findings/{id}/comments` | create: audit_id,finding_title,description,severity,evidence_references; update/review: status,comment |
| Dashboard | GET `/dashboard/summary`, GET `/dashboard/audit-progress`, GET `/dashboard/verification-stats` | authorized-record aggregates and series |
| Reports | POST `/reports/generate/{audit_id}`, GET `/reports`, GET `/reports/{id}/download` | format: pdf or xlsx; immutable snapshot, draft/approved watermark |
| Notifications | GET `/notifications`, PUT `/notifications/{id}/read` | user-owned notification only |
| Administration | GET `/users`, PUT `/users/{id}`, GET `/audit-logs`, GET `/settings` | role change: role; administrator only; directory contains id,name,role |

All audit resources recheck audit membership. Reviewers can inspect assigned projects and record decisions but cannot upload or run checks. Administrators can access all projects; final approval still requires assignment as an independent reviewer. Approved evidence cannot be changed until an auditor explicitly reopens the project. No external communications endpoint exists.

Uploads optionally accept `column_mapping` as a JSON string mapping exact source headers to canonical names, for example `{"Voucher ID":"reference","Gross Value":"amount"}`. Mappings are preserved in document metadata and reapplied on reindex. The upload dialog provides column fields for common canonical targets. Import history is the versioned document inventory, including processing errors and row counts.
