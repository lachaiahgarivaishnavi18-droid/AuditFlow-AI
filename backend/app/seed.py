from pathlib import Path
from werkzeug.security import generate_password_hash
from flask import current_app
from .models import *
from .migrate import upgrade
from .processing import ingest
from .workflow import run
def seed():
    if not current_app.config['DEMO_MODE']: raise RuntimeError('Synthetic seed requires DEMO_MODE=true')
    upgrade()
    if User.query.filter_by(email='auditor@auditflow.demo').first(): return
    users=[]
    for name,role in [('Alex Morgan','auditor'),('Priya Shah','reviewer'),('System Admin','administrator')]:
        user=User(username=name,email=f'{"admin" if role=="administrator" else role}@auditflow.demo',role=role,password_hash=generate_password_hash('AuditFlowDemo!2026')); db.session.add(user); users.append(user)
    db.session.flush(); org=Organization(organization_name='Northstar Manufacturing (SYNTHETIC)',industry='Manufacturing'); db.session.add(org); db.session.flush()
    audit=Audit(project_name='FY 2025-26 Financial Audit',organization_id=org.id,financial_year='2025-26',audit_period_start='2025-04-01',audit_period_end='2026-03-31',assigned_auditor_id=users[0].id,reviewer_id=users[1].id,status='Evidence Collection'); db.session.add(audit); db.session.flush()
    for name,categories in [('Purchase transaction support',['Purchase invoices','Purchase orders','Payment receipts','General ledger']),('Cash and bank reconciliation',['Bank statements','Cash book']),('Ledger completeness',['General ledger','Trial balance'])]: db.session.add(Requirement(audit_id=audit.id,requirement_name=name,required_evidence_type=categories))
    sample=Path(__file__).resolve().parents[2]/'data'/'sample'
    for filename,category in [('purchase_invoices.csv','Purchase invoices'),('bank_statement.csv','Bank statements'),('cash_book.csv','Cash book'),('general_ledger.csv','General ledger'),('receipts.csv','Payment receipts')]: ingest((sample/filename).read_bytes(),filename,audit.id,users[0].id,category,'SYNTHETIC demonstration document')
    db.session.flush(); run(audit.id); db.session.commit()
