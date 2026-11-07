import time, uuid
from typing import TypedDict
from pydantic import BaseModel, Field
from .models import *
from .retrieval import retrieve
from .rules import verify, reconcile, anomalies

class AgentOutput(BaseModel):
    status: str
    summary: str
    data: dict = Field(default_factory=dict)
class WorkflowState(TypedDict, total=False):
    audit_id: int
    run_id: str
    output: dict
    failed: bool
    awaiting_review: bool

def map_evidence(audit_id):
    requirements=Requirement.query.filter_by(audit_id=audit_id).all()
    docs=Document.query.filter_by(audit_id=audit_id,archived=False,processing_status='Processed').all()
    for req in requirements:
        Mapping.query.filter_by(requirement_id=req.id).delete()
        available={d.document_type for d in docs}; missing=set(req.required_evidence_type)-available
        req.status='Missing' if len(missing)==len(req.required_evidence_type) else 'Partially Complete' if missing else 'Requires Manual Review'
        for doc in docs:
            if doc.document_type not in req.required_evidence_type: continue
            chunk=Chunk.query.filter_by(document_id=doc.id).first()
            db.session.add(Mapping(requirement_id=req.id,document_id=doc.id,relevance_score=1,completeness_status=req.status,source_reference={'document_id':doc.id,'version':doc.file_version,'page':chunk.page_number if chunk else None,'section':chunk.section_reference if chunk else 'Document'}))
        existing=EvidenceRequest.query.filter_by(requirement_id=req.id).all()
        for item in existing: item.request_status='Open' if item.requested_document in missing else 'Fulfilled'
        for category in missing:
            if not any(e.requested_document==category for e in existing): db.session.add(EvidenceRequest(audit_id=audit_id,requirement_id=req.id,requested_document=category))
    db.session.flush(); return [r.json() for r in requirements]

def collection(audit_id):
    docs=Document.query.filter_by(audit_id=audit_id,archived=False).all()
    return AgentOutput(status='ok',summary=f'{len(docs)} active documents located.',data={'documents':[d.json() for d in docs]})
def intelligence(audit_id):
    failed=Document.query.filter_by(audit_id=audit_id,archived=False).filter(Document.processing_status!='Processed').all()
    return AgentOutput(status='error' if failed else 'ok',summary='Extraction failures require remediation.' if failed else 'Stored extraction units and structured rows inspected.',data={'failed_documents':[d.id for d in failed]})
def retrieval(audit_id):
    hits=retrieve(audit_id,'invoice bank ledger payment payroll revenue expense',10)
    return AgentOutput(status='ok',summary=f'{len(hits)} source passages retrieved.',data={'sources':hits})
def mapping(audit_id):
    result=map_evidence(audit_id)
    return AgentOutput(status='ok',summary='Evidence categories mapped; document presence requires manual adequacy review.',data={'requirements':result})
def verification(audit_id):
    results=verify(audit_id); reconciliations=reconcile(audit_id)
    return AgentOutput(status='ok',summary='Deterministic checks and reconciliation completed.',data={'verification':results,'reconciliation':reconciliations})
def anomaly(audit_id):
    return AgentOutput(status='ok',summary='Anomaly indicators require investigation.',data=anomalies(audit_id))
def analysis(audit_id):
    # Keep reviewed findings intact; repeated runs do not erase human decisions.
    current=Finding.query.filter_by(audit_id=audit_id,generated=True).all()
    keys={(f.finding_title,str(f.evidence_references)) for f in current}
    count=0
    for item in Verification.query.filter_by(audit_id=audit_id,verification_status='Discrepancy Detected'):
        title=item.verification_type; refs=item.evidence_references
        if (title,str(refs)) not in keys:
            db.session.add(Finding(audit_id=audit_id,finding_title=title,description=item.explanation,severity='High',financial_impact=abs(item.difference) if item.difference is not None else None,evidence_references=refs,generated=True)); count+=1
    for item in Reconciliation.query.filter_by(audit_id=audit_id,status='Discrepancy Detected'):
        title='Reconciliation: '+item.record_type; refs=[item.source_reference,item.matched_reference]
        if (title,str(refs)) not in keys:
            db.session.add(Finding(audit_id=audit_id,finding_title=title,description=f'Compared source amounts differ by {item.difference} {item.currency}.',severity='High',financial_impact=abs(item.difference),evidence_references=refs,generated=True)); count+=1
    audit=db.session.get(Audit,audit_id)
    db.session.add(Notification(user_id=audit.reviewer_id or audit.assigned_auditor_id,audit_id=audit_id,notification_type='Pending review',message=f'Workflow completed with {count} new findings. Human evidence review required.'))
    return AgentOutput(status='ok',summary=f'{count} new evidence-linked findings added; previous decisions retained.',data={'new_findings':count})
def reporting(audit_id):
    audit=db.session.get(Audit,audit_id); audit.status='Under Review'; audit.updated_at=now()
    return AgentOutput(status='awaiting_review',summary='Draft findings consolidated. Assigned reviewer must approve before final reports.',data={'review_checkpoint':True})
def error_handler(audit_id):
    audit=db.session.get(Audit,audit_id); audit.status='Verification Pending'
    db.session.add(Notification(user_id=audit.assigned_auditor_id,audit_id=audit_id,notification_type='Extraction failed',message='Workflow paused. Resolve failed document extraction and rerun.'))
    return AgentOutput(status='error',summary='Workflow stopped because evidence extraction failed. Correct source documents and retry.')

NODES=[('Document Collection Agent',collection),('Document Intelligence Agent',intelligence),('RAG Retrieval Agent',retrieval),('Audit Requirement Mapping Agent',mapping),('Evidence Verification Agent',verification),('Financial Anomaly Detection Agent',anomaly),('Audit Analysis Agent',analysis),('Audit Reporting Agent',reporting)]

def run(audit_id):
    from langgraph.graph import StateGraph, START, END
    run_id=uuid.uuid4().hex
    def wrap(name,fn):
        def execute(state):
            start=time.monotonic(); output=None; error=None
            for attempt in range(2):
                try:
                    with db.session.begin_nested():
                        output=AgentOutput.model_validate(fn(audit_id)).model_dump()
                        if time.monotonic()-start>60: raise TimeoutError('Agent exceeded 60 second completion budget')
                    error=None; break
                except Exception as exc: error=f'{type(exc).__name__}: {exc}'
            status='error' if error else output['status']
            version='deterministic-local-v1'
            if name=='Financial Anomaly Detection Agent':
                import sklearn
                version=f'IsolationForest/scikit-learn-{sklearn.__version__}'
            if name=='RAG Retrieval Agent':
                from .embeddings import model_version
                version=model_version()
            db.session.add(AgentLog(audit_id=audit_id,run_id=run_id,agent_name=name,execution_status=status,input_summary={'audit_id':audit_id},output_summary=output,error_message=error,execution_time=round(time.monotonic()-start,4),model_version=version))
            db.session.flush()
            return {'output':output or {'status':'error','summary':error},'failed':status=='error','awaiting_review':status=='awaiting_review'}
        return execute
    graph=StateGraph(WorkflowState)
    for name,fn in NODES: graph.add_node(name,wrap(name,fn))
    graph.add_node('Extraction remediation',wrap('Extraction remediation',error_handler))
    graph.add_edge(START,NODES[0][0])
    for i,(name,_) in enumerate(NODES):
        target=NODES[i+1][0] if i+1<len(NODES) else END
        graph.add_conditional_edges(name,lambda state:'error' if state.get('failed') else 'next',{'error':'Extraction remediation','next':target})
    graph.add_edge('Extraction remediation',END)
    result=graph.compile().invoke({'audit_id':audit_id,'run_id':run_id,'failed':False},config={'recursion_limit':15})
    db.session.flush(); return result
