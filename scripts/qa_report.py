"""Generate the actual synthetic audit report for visual QA."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app import create_app
from app.models import Audit,Report
from app.reports import snapshot,pdf_bytes
app=create_app()
with app.app_context():
    audit=Audit.query.first()
    if not audit:raise RuntimeError('Seed the demo first')
    report=Report(id=0,audit_id=audit.id,format='pdf',snapshot=snapshot(audit.id),approved_by=None)
    output=ROOT/'output'/'pdf';output.mkdir(parents=True,exist_ok=True)
    target=output/'auditflow-demo.pdf';target.write_bytes(pdf_bytes(report))
    import pymupdf
    with pymupdf.open(target) as pdf:
        assert all(p.get_text().strip() for p in pdf)
        assert 'DRAFT' in pdf[0].get_text()
        print(f'Generated {len(pdf)} pages: {target}')
