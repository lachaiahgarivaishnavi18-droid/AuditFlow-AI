# User manual

**Auditor:** Create a project, choose its reviewer and period. The active audit selector controls all evidence and analysis pages. Upload labeled evidence, inspect extraction status and source text, and correct parser errors by supplying a new document version or normalized CSV/XLSX. Files with the same name receive incremented versions; originals remain downloadable by authorized users.

**Evidence mapping:** Default requirements cover purchases, bank/cash book and ledger/trial balance. Add objectives and expected categories through Add requirement. Map evidence to create citations and internal missing-document requests. Presence yields Requires Manual Review rather than automatic completeness.

**Assistant:** Ask for a term, reference or document content. Local mode returns matching source passages and relevance scores. Click Doc citations to inspect original context. This assistant does not automatically compute ad-hoc amounts or interpret a fraud allegation; use verification and reconciliation for supported computations.

**Analysis:** Run verification or reconciliation individually, or use Run audit workflow for the eight-stage LangGraph sequence. Inspect execution history to see outputs, timing, versions and errors. Anomaly indicators are suggested investigation targets.

**Findings:** Add human observations and comments. Submit findings for review. Each generated discrepancy links to original document rows. Accepted/Rejected/Resolved decisions require the assigned independent reviewer and a rationale. Repeated workflow runs preserve prior human decisions.

**Reviewer:** Inspect findings and cited sources, record decisions, then confirm evidence adequacy on the mapping page. All requirements must be reviewed complete and all findings reviewed before project approval. Unresolved or missing supporting evidence should remain open; use the internal request list to track collection.

**Reports:** Generate PDF or Excel at any time. Before final approval exports are draft. Each report freezes the records and review status at generation time; later changes never rewrite earlier snapshots.

**Administrator:** Manage user roles and inspect system audit logs. Administrators still need assignment as an independent reviewer to approve an audit. Public registration cannot create privileged users.

**Notifications/settings:** Read in-app processing/review notices. Configure matching tolerance and dates. Reopen an approved audit explicitly to add evidence; rerun checks and obtain a new review before finalization.
