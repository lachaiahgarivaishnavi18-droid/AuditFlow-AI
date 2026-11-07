# Validation scope

Final local run: **18 backend tests passed**, **17 frontend tests passed**, and the Vite production build succeeded. Build output separates React, chart dependencies and application code. The Python application and script sources also passed compile checks.

The application was exercised locally with Python 3.12, SQLite, FAISS, LangGraph and a built React frontend. Tests include generated real PDF/DOCX/XLSX parser inputs and structured synthetic evidence. The browser check covered demo login, database dashboard values, cited retrieval and the document provenance modal.

Backend regression tests verify project isolation, role restrictions, session revocation, immutable originals and versioning, unsafe archives, extraction-error routing, evidence mapping, exact financial calculations, SQLite large-decimal persistence, reconciliation currency/date constraints, repeatable anomaly indicators, graph node logs, reviewer approval gates, draft PDF/XLSX downloads and rejection of invented LLM quotes. Assistant-tool tests cover amount thresholds, duplicate keys and invalidation of stale results after new evidence. Additional regressions cover empty-message agent exceptions, semantic encoder integration and preservation of custom import column mappings.

Frontend Vitest tests exercise API authorization/multipart/error contracts and React workflows for login, source preview, cited search, verification, reconciliation, agent execution, upload entry and report generation/download. UI workflows use mocked API responses; they complement actual backend integration tests rather than representing a browser-driven end-to-end test suite.

The actual seeded PDF export was rendered with Poppler and all pages visually inspected in a contact sheet. Core exports have headings, source IDs/locations and a draft review status.

Not locally executed: Docker build/Compose/PostgreSQL integration (Docker was unavailable), paid live model API requests, real Tesseract OCR (the executable was unavailable), semantic embedding model evaluation, load/concurrency testing and external malware scanning. The OCR adapter path and optional LLM output validator are unit-tested using controlled substitutes. These are verification limits, not claims of completed production qualification.
