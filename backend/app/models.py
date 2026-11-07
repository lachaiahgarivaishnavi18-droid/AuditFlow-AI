from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint
from sqlalchemy.types import TypeDecorator, String, Numeric
from decimal import Decimal
db = SQLAlchemy()
class ExactMoney(TypeDecorator):
    """Avoid SQLite's binary floating coercion; PostgreSQL uses NUMERIC."""
    impl=Numeric(24,4)
    cache_ok=True
    def load_dialect_impl(self,dialect): return dialect.type_descriptor(String(40) if dialect.name=='sqlite' else Numeric(24,4))
    def process_bind_param(self,value,dialect): return None if value is None else str(value) if dialect.name=='sqlite' else Decimal(str(value))
    def process_result_value(self,value,dialect): return None if value is None else Decimal(str(value))
def now(): return datetime.now(timezone.utc).isoformat()

class Base(db.Model):
    __abstract__ = True
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.String(40), default=now, nullable=False)
    def json(self):
        from decimal import Decimal
        return {c.name: str(getattr(self,c.name)) if isinstance(getattr(self,c.name),Decimal) else getattr(self,c.name) for c in self.__table__.columns if c.name not in ('password_hash','file_path')}

class User(Base):
    __tablename__='users'
    username=db.Column(db.String(100),nullable=False)
    email=db.Column(db.String(255),unique=True,nullable=False)
    password_hash=db.Column(db.String(255),nullable=False)
    role=db.Column(db.String(20),nullable=False,default='auditor')
class Session(Base):
    __tablename__='sessions'
    user_id=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=False,index=True)
    token_id=db.Column(db.String(64),unique=True,nullable=False)
    revoked=db.Column(db.Boolean,default=False,nullable=False)
class Organization(Base):
    __tablename__='organizations'
    organization_name=db.Column(db.String(200),nullable=False)
    registration_number=db.Column(db.String(100))
    industry=db.Column(db.String(100))
class Audit(Base):
    __tablename__='audit_projects'
    project_name=db.Column(db.String(200),nullable=False)
    organization_id=db.Column(db.Integer,db.ForeignKey('organizations.id'),nullable=False)
    financial_year=db.Column(db.String(20),nullable=False)
    audit_period_start=db.Column(db.String(10),nullable=False)
    audit_period_end=db.Column(db.String(10),nullable=False)
    audit_type=db.Column(db.String(100),default='Financial statement audit')
    assigned_auditor_id=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=False,index=True)
    reviewer_id=db.Column(db.Integer,db.ForeignKey('users.id'),index=True)
    status=db.Column(db.String(40),default='Draft')
    updated_at=db.Column(db.String(40),default=now)
    settings=db.Column(db.JSON,default=lambda:{'tolerance':'0.01','date_window':7})
class Document(Base):
    __tablename__='documents'
    audit_id=db.Column(db.Integer,db.ForeignKey('audit_projects.id'),nullable=False,index=True)
    document_name=db.Column(db.String(255),nullable=False)
    document_type=db.Column(db.String(60),nullable=False)
    file_path=db.Column(db.String(500),nullable=False)
    file_hash=db.Column(db.String(64),nullable=False,index=True)
    file_version=db.Column(db.Integer,default=1,nullable=False)
    previous_version_id=db.Column(db.Integer,db.ForeignKey('documents.id'))
    uploaded_by=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=False)
    processing_status=db.Column(db.String(30),default='Pending')
    extraction_confidence=db.Column(db.Float)
    extraction_method=db.Column(db.String(80))
    processing_errors=db.Column(db.Text)
    description=db.Column(db.Text,default='')
    archived=db.Column(db.Boolean,default=False)
    metadata_json=db.Column(db.JSON,default=dict)
    __table_args__=(UniqueConstraint('audit_id','document_name','file_version'),)
class Chunk(Base):
    __tablename__='document_chunks'
    document_id=db.Column(db.Integer,db.ForeignKey('documents.id'),nullable=False,index=True)
    chunk_text=db.Column(db.Text,nullable=False)
    page_number=db.Column(db.Integer)
    section_reference=db.Column(db.String(200))
    embedding_reference=db.Column(db.JSON)
class DocumentBlob(Base):
    __tablename__='document_blobs'
    document_id=db.Column(db.Integer,db.ForeignKey('documents.id'),unique=True,nullable=False,index=True)
    content=db.Column(db.LargeBinary,nullable=False)
class Record(Base):
    __tablename__='financial_records'
    document_id=db.Column(db.Integer,db.ForeignKey('documents.id'),nullable=False,index=True)
    source_reference=db.Column(db.String(200),nullable=False)
    values=db.Column(db.JSON,nullable=False)
class Requirement(Base):
    __tablename__='audit_requirements'
    audit_id=db.Column(db.Integer,db.ForeignKey('audit_projects.id'),nullable=False,index=True)
    requirement_name=db.Column(db.String(200),nullable=False)
    requirement_description=db.Column(db.Text,default='')
    required_evidence_type=db.Column(db.JSON,nullable=False)
    status=db.Column(db.String(40),default='Missing')
class Mapping(Base):
    __tablename__='evidence_mappings'
    requirement_id=db.Column(db.Integer,db.ForeignKey('audit_requirements.id'),nullable=False,index=True)
    document_id=db.Column(db.Integer,db.ForeignKey('documents.id'),nullable=False)
    relevance_score=db.Column(db.Float)
    completeness_status=db.Column(db.String(40))
    source_reference=db.Column(db.JSON)
class Verification(Base):
    __tablename__='verification_results'
    audit_id=db.Column(db.Integer,db.ForeignKey('audit_projects.id'),nullable=False,index=True)
    verification_type=db.Column(db.String(100),nullable=False)
    source_document_id=db.Column(db.Integer,db.ForeignKey('documents.id'),nullable=False)
    comparison_document_id=db.Column(db.Integer,db.ForeignKey('documents.id'))
    expected_value=db.Column(ExactMoney())
    actual_value=db.Column(ExactMoney())
    difference=db.Column(ExactMoney())
    verification_status=db.Column(db.String(40),nullable=False)
    explanation=db.Column(db.Text,nullable=False)
    evidence_references=db.Column(db.JSON,default=list)
class Reconciliation(Base):
    __tablename__='reconciliation_records'
    audit_id=db.Column(db.Integer,db.ForeignKey('audit_projects.id'),nullable=False,index=True)
    record_type=db.Column(db.String(100))
    source_reference=db.Column(db.JSON)
    matched_reference=db.Column(db.JSON)
    expected_amount=db.Column(ExactMoney())
    actual_amount=db.Column(ExactMoney())
    difference=db.Column(ExactMoney())
    currency=db.Column(db.String(10))
    status=db.Column(db.String(40))
class Finding(Base):
    __tablename__='audit_findings'
    audit_id=db.Column(db.Integer,db.ForeignKey('audit_projects.id'),nullable=False,index=True)
    finding_title=db.Column(db.String(200),nullable=False)
    description=db.Column(db.Text,nullable=False)
    severity=db.Column(db.String(20),default='Medium')
    financial_impact=db.Column(ExactMoney())
    recommendation=db.Column(db.Text,default='Request supporting evidence and review source records.')
    status=db.Column(db.String(40),default='Open')
    evidence_references=db.Column(db.JSON,default=list)
    generated=db.Column(db.Boolean,default=False)
    reviewer_id=db.Column(db.Integer,db.ForeignKey('users.id'))
    reviewer_comments=db.Column(db.Text)
class AgentLog(Base):
    __tablename__='agent_logs'
    audit_id=db.Column(db.Integer,db.ForeignKey('audit_projects.id'),nullable=False,index=True)
    run_id=db.Column(db.String(64),index=True)
    agent_name=db.Column(db.String(100))
    execution_status=db.Column(db.String(40))
    input_summary=db.Column(db.JSON)
    output_summary=db.Column(db.JSON)
    error_message=db.Column(db.Text)
    execution_time=db.Column(db.Float)
    prompt_version=db.Column(db.String(40),default='rules-v1')
    model_version=db.Column(db.String(80),default='deterministic-local-v1')
class Comment(Base):
    __tablename__='analyst_comments'
    audit_id=db.Column(db.Integer,db.ForeignKey('audit_projects.id'),nullable=False,index=True)
    finding_id=db.Column(db.Integer,db.ForeignKey('audit_findings.id'),nullable=False)
    user_id=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=False)
    comment=db.Column(db.Text,nullable=False)
class AuditLog(Base):
    __tablename__='audit_logs'
    user_id=db.Column(db.Integer,db.ForeignKey('users.id'))
    action=db.Column(db.String(100),nullable=False)
    resource_type=db.Column(db.String(100))
    resource_id=db.Column(db.Integer)
    details=db.Column(db.JSON)
class EvidenceRequest(Base):
    __tablename__='evidence_requests'
    audit_id=db.Column(db.Integer,db.ForeignKey('audit_projects.id'),nullable=False,index=True)
    requirement_id=db.Column(db.Integer,db.ForeignKey('audit_requirements.id'))
    requested_document=db.Column(db.String(200),nullable=False)
    request_status=db.Column(db.String(30),default='Open')
class Notification(Base):
    __tablename__='notifications'
    user_id=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=False,index=True)
    audit_id=db.Column(db.Integer,db.ForeignKey('audit_projects.id'))
    notification_type=db.Column(db.String(50))
    message=db.Column(db.Text)
    is_read=db.Column(db.Boolean,default=False)
class Report(Base):
    __tablename__='reports'
    audit_id=db.Column(db.Integer,db.ForeignKey('audit_projects.id'),nullable=False,index=True)
    format=db.Column(db.String(10),nullable=False)
    snapshot=db.Column(db.JSON,nullable=False)
    approved_by=db.Column(db.Integer,db.ForeignKey('users.id'))
class RetrievalHistory(Base):
    __tablename__='retrieval_history'
    audit_id=db.Column(db.Integer,db.ForeignKey('audit_projects.id'),nullable=False,index=True)
    user_id=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=False)
    query=db.Column(db.Text)
    response=db.Column(db.JSON)
