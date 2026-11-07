import os, secrets, time, uuid, io, json,tempfile
from pathlib import Path
from datetime import datetime, timedelta, timezone, date
from functools import wraps
from collections import defaultdict, deque, Counter
import jwt
import click
from sqlalchemy import event
from sqlalchemy.engine import Engine
import sqlite3

@event.listens_for(Engine,'connect')
def sqlite_foreign_keys(connection,record):
    if isinstance(connection,sqlite3.Connection): connection.execute('PRAGMA foreign_keys=ON')
from flask import Flask, request, jsonify, g, send_file, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.exceptions import HTTPException
from pydantic import BaseModel, Field, ValidationError, ConfigDict
from dotenv import load_dotenv
from .models import *
from .processing import ingest, unpack, process, CATEGORIES, money
from .retrieval import answer
from .workflow import run, map_evidence
from .rules import verify, reconcile, anomalies
from .reports import snapshot, pdf_bytes, xlsx_bytes

ROOT=Path(__file__).resolve().parents[2]
class ApiError(Exception):
    def __init__(self,message,status=400): self.message=message; self.status=status
class AuditInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    project_name:str=Field(min_length=2,max_length=200)
    organization_name:str=Field(min_length=2,max_length=200)
    financial_year:str=Field(min_length=4,max_length=20)
    audit_period_start:date
    audit_period_end:date
    audit_type:str='Financial statement audit'
    assigned_auditor_id:int|None=None
    reviewer_id:int|None=None
class QueryInput(BaseModel):
    audit_id:int
    query:str=Field(min_length=2,max_length=2000)
    top_k:int=Field(default=5,ge=1,le=20)
    category:str|None=None
    document_id:int|None=None

def body():
    data=request.get_json(silent=True)
    if not isinstance(data,dict): raise ApiError('A JSON object is required')
    return data
def authenticated(fn):
    @wraps(fn)
    def wrapper(*args,**kwargs):
        try:
            token=request.headers.get('Authorization','').removeprefix('Bearer ')
            claims=jwt.decode(token,g.app.config['SECRET_KEY'],algorithms=['HS256'],options={'require':['exp','sub','jti']})
            session=Session.query.filter_by(token_id=claims['jti'],revoked=False).first()
            user=db.session.get(User,int(claims['sub']))
            if not session or not user or session.user_id!=user.id: raise ValueError()
            g.user=user
        except (jwt.PyJWTError,ValueError,TypeError): raise ApiError('Authentication required',401)
        return fn(*args,**kwargs)
    return wrapper
def role(*roles):
    if g.user.role not in roles: raise ApiError('Insufficient permissions',403)
def access(audit_id,write=False):
    audit=db.session.get(Audit,audit_id)
    if not audit: raise ApiError('Audit not found',404)
    if g.user.role!='administrator' and g.user.id not in (audit.assigned_auditor_id,audit.reviewer_id): raise ApiError('Audit access denied',403)
    if write:
        role('auditor','administrator')
        if audit.status in ('Approved','Completed'): raise ApiError('Reopen the audit before changing evidence or results',409)
    return audit
def visible():
    query=Audit.query
    if g.user.role!='administrator': query=query.filter(db.or_(Audit.assigned_auditor_id==g.user.id,Audit.reviewer_id==g.user.id))
    return query
def record_log(action,resource_type,resource_id,details=None):
    db.session.add(AuditLog(user_id=g.user.id,action=action,resource_type=resource_type,resource_id=resource_id,details=details))
def commit(action=None,resource='audit',id=None,details=None):
    if action: record_log(action,resource,id,details)
    db.session.commit()
def paginated(query):
    try: page=max(1,int(request.args.get('page',1))); size=min(100,max(1,int(request.args.get('per_page',25))))
    except ValueError: raise ApiError('Invalid pagination')
    total=query.count(); rows=query.order_by(query.column_descriptions[0]['entity'].id.desc()).offset((page-1)*size).limit(size).all()
    return jsonify(items=[x.json() for x in rows],total=total,page=page,per_page=size)
def scoped_doc(id,write=False):
    doc=db.session.get(Document,id)
    if not doc: raise ApiError('Document not found',404)
    access(doc.audit_id,write); return doc
def invalidate(audit):
    audit.status='Evidence Collection'; audit.updated_at=now()
    Verification.query.filter_by(audit_id=audit.id).delete()
    Reconciliation.query.filter_by(audit_id=audit.id).delete()
    map_evidence(audit.id)

def create_app(config=None):
    load_dotenv(ROOT/'.env'); app=Flask(__name__,static_folder=None)
    hosted=os.getenv('VERCEL')=='1'
    data=Path(tempfile.gettempdir())/'auditflow' if hosted else ROOT/'data'; data.mkdir(parents=True,exist_ok=True)
    demo=os.getenv('DEMO_MODE','true').lower()=='true'
    secret=os.getenv('SECRET_KEY')
    if not secret:
        secret=secrets.token_hex(32)
    if not demo and (len(secret)<32 or secret.startswith('replace-')): raise RuntimeError('Production requires a strong SECRET_KEY')
    app.config.update(SECRET_KEY=secret,SQLALCHEMY_DATABASE_URI=os.getenv('DATABASE_URL',f'sqlite:///{data / "auditflow.db"}'),SQLALCHEMY_TRACK_MODIFICATIONS=False,MAX_CONTENT_LENGTH=50*1024*1024,MAX_FILE_BYTES=int(os.getenv('MAX_UPLOAD_MB','20'))*1024*1024,UPLOAD_DIR=str(data/'uploads'),DEMO_MODE=demo,TESSERACT_CMD=os.getenv('TESSERACT_CMD'),MALWARE_SCANNER=os.getenv('MALWARE_SCANNER'))
    if config: app.config.update(config)
    uri=app.config['SQLALCHEMY_DATABASE_URI']
    if uri.startswith('postgres://'):uri='postgresql+psycopg://'+uri[len('postgres://'):]
    elif uri.startswith('postgresql://'):uri='postgresql+psycopg://'+uri[len('postgresql://'):]
    app.config['SQLALCHEMY_DATABASE_URI']=uri
    app.config['STORE_ORIGINALS_IN_DB']=hosted or os.getenv('STORE_ORIGINALS_IN_DB','false').lower()=='true'
    if hosted:
        app.config['MAX_CONTENT_LENGTH']=4*1024*1024
        app.config['MAX_FILE_BYTES']=3*1024*1024
        app.config['SQLALCHEMY_ENGINE_OPTIONS']={'pool_pre_ping':True,'pool_recycle':240}
    Path(app.config['UPLOAD_DIR']).mkdir(parents=True,exist_ok=True); db.init_app(app)
    buckets=defaultdict(deque)
    @app.before_request
    def before():
        g.app=app
        if request.path.startswith('/api/'):
            key=(request.remote_addr,request.path.startswith('/api/auth/')); queue=buckets[key]; stamp=time.monotonic(); limit=30 if key[1] else 240
            while queue and queue[0]<stamp-60: queue.popleft()
            if len(queue)>=limit: raise ApiError('Rate limit exceeded. Retry after one minute.',429)
            queue.append(stamp)
    @app.after_request
    def secure(response):
        response.headers['X-Content-Type-Options']='nosniff'; response.headers['X-Frame-Options']='DENY'; response.headers['Referrer-Policy']='same-origin'
        if request.path.startswith('/api/'): response.headers['Cache-Control']='no-store'
        return response
    @app.errorhandler(ApiError)
    def api_error(exc): db.session.rollback(); return jsonify(error=exc.message,code=exc.status),exc.status
    @app.errorhandler(ValidationError)
    def validation_error(exc): db.session.rollback(); return jsonify(error='Input validation failed',code=400,details=[{'field':'.'.join(str(x) for x in e['loc']),'message':e['msg']} for e in exc.errors()]),400
    @app.errorhandler(ValueError)
    def value_error(exc): db.session.rollback(); return jsonify(error=str(exc),code=400),400
    @app.errorhandler(HTTPException)
    def http_error(exc): return jsonify(error=exc.description,code=exc.code),exc.code
    @app.errorhandler(Exception)
    def unexpected(exc):
        db.session.rollback(); app.logger.exception('Request failed'); return jsonify(error='Internal error. Consult server logs.',code=500),500

    @app.get('/api/health')
    def health(): return jsonify(status='ok',mode='demo' if app.config['DEMO_MODE'] else 'configured',retrieval='FAISS local hashing + keyword',llm_enabled=bool(os.getenv('ANTHROPIC_API_KEY') and os.getenv('LLM_MODEL')))
    @app.post('/api/auth/register')
    def register():
        data=body(); email=str(data.get('email','')).strip().lower(); password=str(data.get('password','')); username=str(data.get('username','')).strip()
        if '@' not in email or len(email)>255 or len(password)<12 or len(password)>128 or not 2<=len(username)<=100: raise ApiError('Valid email, name and password of 12-128 characters are required')
        if User.query.filter_by(email=email).first(): raise ApiError('Email already registered',409)
        user=User(email=email,username=username,password_hash=generate_password_hash(password),role='auditor'); db.session.add(user); db.session.flush(); db.session.add(AuditLog(user_id=user.id,action='register',resource_type='user',resource_id=user.id)); db.session.commit(); return jsonify(user=user.json()),201
    @app.post('/api/auth/login')
    def login():
        data=body(); user=User.query.filter_by(email=str(data.get('email','')).strip().lower()).first()
        if not user or not check_password_hash(user.password_hash,str(data.get('password',''))): raise ApiError('Invalid email or password',401)
        token_id=uuid.uuid4().hex; db.session.add(Session(user_id=user.id,token_id=token_id)); db.session.add(AuditLog(user_id=user.id,action='login',resource_type='user',resource_id=user.id)); db.session.commit()
        token=jwt.encode({'sub':str(user.id),'jti':token_id,'iat':datetime.now(timezone.utc),'exp':datetime.now(timezone.utc)+timedelta(hours=8)},app.config['SECRET_KEY'],algorithm='HS256')
        return jsonify(token=token,user=user.json())
    @app.get('/api/auth/me')
    @authenticated
    def me(): return jsonify(g.user.json())
    @app.post('/api/auth/logout')
    @authenticated
    def logout():
        claims=jwt.decode(request.headers['Authorization'].removeprefix('Bearer '),app.config['SECRET_KEY'],algorithms=['HS256']); Session.query.filter_by(token_id=claims['jti']).first().revoked=True; commit('logout','user',g.user.id); return jsonify(ok=True)

    @app.get('/api/users')
    @authenticated
    def users():
        # Assignment directory excludes email addresses and password hashes.
        return jsonify(items=[{'id':u.id,'username':u.username,'role':u.role} for u in User.query.all()])
    @app.put('/api/users/<int:id>')
    @authenticated
    def update_user(id):
        role('administrator'); data=body(); user=db.session.get(User,id)
        if not user: raise ApiError('User not found',404)
        new_role=data.get('role')
        if new_role not in ('administrator','auditor','reviewer'): raise ApiError('Invalid role')
        if id==g.user.id: raise ApiError('Cannot change your own administrator role')
        user.role=new_role; Session.query.filter_by(user_id=id).update({'revoked':True}); commit('change role','user',id,{'role':new_role}); return jsonify(user.json())
    @app.get('/api/audits')
    @authenticated
    def audits():
        query=visible(); search=request.args.get('q','')
        if search: query=query.filter(Audit.project_name.ilike('%'+search+'%'))
        return paginated(query)
    @app.post('/api/audits')
    @authenticated
    def create_audit():
        role('auditor','administrator'); data=AuditInput.model_validate(body())
        if data.audit_period_start>data.audit_period_end: raise ApiError('Audit start must precede end')
        assigned=data.assigned_auditor_id or g.user.id
        if assigned!=g.user.id and g.user.role!='administrator': raise ApiError('Only administrators can assign another auditor',403)
        assigned_user=db.session.get(User,assigned)
        if not assigned_user or assigned_user.role not in ('auditor','administrator'): raise ApiError('Invalid assigned auditor')
        if data.reviewer_id:
            reviewer=db.session.get(User,data.reviewer_id)
            if not reviewer or reviewer.role not in ('reviewer','administrator') or reviewer.id==assigned: raise ApiError('Choose an independent reviewer')
        org=Organization(organization_name=data.organization_name); db.session.add(org); db.session.flush()
        audit=Audit(project_name=data.project_name,organization_id=org.id,financial_year=data.financial_year,audit_period_start=data.audit_period_start.isoformat(),audit_period_end=data.audit_period_end.isoformat(),audit_type=data.audit_type,assigned_auditor_id=assigned,reviewer_id=data.reviewer_id)
        db.session.add(audit); db.session.flush()
        for name,categories in [('Purchase transaction support',['Purchase invoices','Purchase orders','Payment receipts','General ledger']),('Cash and bank completeness',['Bank statements','Cash book']),('Ledger and trial balance',['General ledger','Trial balance'])]: db.session.add(Requirement(audit_id=audit.id,requirement_name=name,required_evidence_type=categories))
        commit('create','audit',audit.id); return jsonify(audit.json()),201
    @app.get('/api/audits/<int:id>')
    @authenticated
    def get_audit(id):
        audit=access(id); result=audit.json(); result['organization']=db.session.get(Organization,audit.organization_id).json(); return jsonify(result)
    @app.put('/api/audits/<int:id>')
    @authenticated
    def update_audit(id):
        audit=access(id); role('auditor','administrator'); data=body()
        for key in ['project_name','audit_type']:
            if key in data:
                if not isinstance(data[key],str) or not 2<=len(data[key])<=200: raise ApiError('Invalid '+key)
                setattr(audit,key,data[key])
        if 'reviewer_id' in data:
            reviewer=db.session.get(User,int(data['reviewer_id']))
            if not reviewer or reviewer.role not in ('reviewer','administrator') or reviewer.id==audit.assigned_auditor_id: raise ApiError('Independent reviewer required')
            audit.reviewer_id=reviewer.id
        if 'settings' in data:
            settings=data['settings']; tolerance=money(settings.get('tolerance','0.01')); window=int(settings.get('date_window',7))
            if tolerance<0 or tolerance>10000 or not 0<=window<=90: raise ApiError('Invalid tolerance or date window')
            if not isinstance(settings.get('disabled_rules',[]),list): raise ApiError('disabled_rules must be an array')
            audit.settings={'tolerance':str(tolerance),'date_window':window,'disabled_rules':settings.get('disabled_rules',[])}
            invalidate(audit)
        if 'status' in data:
            if data['status'] not in ['Draft','In Progress','Evidence Collection','Verification Pending','Under Review','Completed']: raise ApiError('Approval requires reviewer checkpoint')
            if data['status']=='Completed' and audit.status!='Approved': raise ApiError('Only approved audits may complete',409)
            audit.status=data['status']
        audit.updated_at=now(); commit('update','audit',id,data); return jsonify(audit.json())
    @app.delete('/api/audits/<int:id>')
    @authenticated
    def delete_audit(id):
        audit=access(id); role('administrator'); audit.status='Completed'; commit('archive project','audit',id); return jsonify(ok=True,note='Project archived; evidence and history retained.')
    @app.post('/api/audits/<int:id>/approve')
    @authenticated
    def approve_audit(id):
        audit=access(id); role('reviewer','administrator'); data=body()
        if g.user.id!=audit.reviewer_id or g.user.id==audit.assigned_auditor_id: raise ApiError('Assigned independent reviewer required',403)
        if audit.status!='Under Review': raise ApiError('Run the workflow and submit the audit for review first',409)
        if Finding.query.filter_by(audit_id=id).filter(Finding.status.notin_(['Accepted','Rejected','Resolved'])).count(): raise ApiError('Review every open finding before approval',409)
        if Requirement.query.filter_by(audit_id=id).filter(Requirement.status!='Complete').count(): raise ApiError('All requirements require documented completeness review',409)
        if not str(data.get('comment','')).strip(): raise ApiError('Reviewer rationale required')
        audit.status='Approved'; commit('approve','audit',id,{'comment':data['comment']}); return jsonify(audit.json())

    @app.post('/api/documents/upload')
    @app.post('/api/documents/bulk-upload')
    @authenticated
    def upload():
        try: audit_id=int(request.form.get('audit_id',''))
        except ValueError: raise ApiError('audit_id is required')
        audit=access(audit_id,True); files=request.files.getlist('files') or request.files.getlist('file')
        if not files or len(files)>30: raise ApiError('Select 1-30 files')
        pending=[]
        for file in files:
            data=file.read(app.config['MAX_FILE_BYTES']+1)
            if len(data)>app.config['MAX_FILE_BYTES']: raise ApiError('File exceeds size limit',413)
            pending.extend(unpack(data) if file.filename.lower().endswith('.zip') else [(file.filename,data)])
        if len(pending)>30: raise ApiError('Maximum 30 files per request')
        results=[]
        try: column_mapping=json.loads(request.form.get('column_mapping','{}'))
        except json.JSONDecodeError: raise ApiError('Column mapping must be a JSON object')
        if not isinstance(column_mapping,dict) or any(not isinstance(k,str) or not isinstance(v,str) for k,v in column_mapping.items()) or len(set(column_mapping.values()))!=len(column_mapping): raise ApiError('Column mappings must have unique text targets')
        for name,data in pending:
            doc=ingest(data,name,audit_id,g.user.id,request.form.get('category','Auto'),request.form.get('description',''),column_mapping=column_mapping); results.append(doc.json())
            if doc.processing_status=='Failed': db.session.add(Notification(user_id=g.user.id,audit_id=audit_id,notification_type='Extraction failed',message=f'{doc.document_name}: {doc.processing_errors}'))
        invalidate(audit); commit('upload documents','audit',audit_id,{'document_ids':[d['id'] for d in results]}); return jsonify(items=results),201
    @app.get('/api/documents')
    @authenticated
    def documents():
        ids=[a.id for a in visible()]; query=Document.query.filter(Document.audit_id.in_(ids))
        if request.args.get('audit_id'): access(int(request.args['audit_id'])); query=query.filter_by(audit_id=int(request.args['audit_id']))
        if request.args.get('archived')!='true': query=query.filter_by(archived=False)
        if request.args.get('category'): query=query.filter_by(document_type=request.args['category'])
        return paginated(query)
    @app.get('/api/documents/<int:id>')
    @app.get('/api/documents/<int:id>/status')
    @authenticated
    def document(id): return jsonify(scoped_doc(id).json())
    @app.get('/api/documents/<int:id>/extracted-text')
    @authenticated
    def text(id):
        scoped_doc(id); return jsonify(chunks=[c.json() for c in Chunk.query.filter_by(document_id=id)],records=[r.json() for r in Record.query.filter_by(document_id=id)])
    @app.get('/api/documents/<int:id>/download')
    @authenticated
    def download_doc(id):
        doc=scoped_doc(id); blob=DocumentBlob.query.filter_by(document_id=id).first(); record_log('download','document',id); db.session.commit(); return send_file(io.BytesIO(blob.content) if blob else doc.file_path,as_attachment=True,download_name=doc.document_name)
    @app.delete('/api/documents/<int:id>')
    @authenticated
    def archive_doc(id):
        doc=scoped_doc(id,True); doc.archived=True; invalidate(db.session.get(Audit,doc.audit_id)); commit('archive','document',id); return jsonify(ok=True)
    @app.post('/api/rag/index/<int:id>')
    @authenticated
    def index_doc(id):
        doc=scoped_doc(id,True); process(doc); invalidate(db.session.get(Audit,doc.audit_id)); commit('reindex','document',id); return jsonify(doc.json())
    @app.post('/api/rag/reindex/<int:id>')
    @authenticated
    def reindex(id):
        audit=access(id,True)
        for doc in Document.query.filter_by(audit_id=id,archived=False): process(doc)
        invalidate(audit); commit('reindex','audit',id); return jsonify(ok=True)
    @app.post('/api/rag/query')
    @authenticated
    def query():
        data=QueryInput.model_validate(body()); access(data.audit_id)
        if data.document_id:
            doc=scoped_doc(data.document_id)
            if doc.audit_id!=data.audit_id: raise ApiError('Document does not belong to audit')
        result=answer(data.audit_id,g.user.id,data.query,data.top_k,data.category,data.document_id); commit('retrieve','audit',data.audit_id); return jsonify(result)
    @app.get('/api/rag/retrieval-history/<int:id>')
    @authenticated
    def retrieval_history(id): access(id); return paginated(RetrievalHistory.query.filter_by(audit_id=id))

    @app.get('/api/evidence/<int:id>')
    @app.get('/api/evidence/missing/<int:id>')
    @app.get('/api/evidence/coverage/<int:id>')
    @authenticated
    def evidence(id):
        access(id); reqs=Requirement.query.filter_by(audit_id=id).all(); ids=[r.id for r in reqs]
        return jsonify(requirements=[r.json() for r in reqs],mappings=[m.json() for m in Mapping.query.filter(Mapping.requirement_id.in_(ids))] if ids else [],requests=[r.json() for r in EvidenceRequest.query.filter_by(audit_id=id)],complete=sum(r.status=='Complete' for r in reqs),total=len(reqs))
    @app.post('/api/evidence/map')
    @authenticated
    def evidence_map():
        data=body(); id=int(data.get('audit_id',0)); access(id,True); result=map_evidence(id); commit('map evidence','audit',id); return jsonify(items=result)
    @app.post('/api/requirements')
    @authenticated
    def add_requirement():
        data=body(); audit=access(int(data.get('audit_id',0)),True); categories=data.get('required_evidence_type',[])
        if not categories or not isinstance(categories,list) or any(c not in CATEGORIES for c in categories): raise ApiError('Select valid evidence categories')
        name=str(data.get('requirement_name','')).strip()
        if not 2<=len(name)<=200: raise ApiError('Requirement name required')
        req=Requirement(audit_id=audit.id,requirement_name=name,requirement_description=str(data.get('requirement_description',''))[:5000],required_evidence_type=categories); db.session.add(req); invalidate(audit); db.session.flush(); commit('create requirement','audit',audit.id); return jsonify(req.json()),201
    @app.post('/api/requirements/<int:id>/review')
    @authenticated
    def review_requirement(id):
        req=db.session.get(Requirement,id)
        if not req: raise ApiError('Requirement not found',404)
        audit=access(req.audit_id); role('reviewer','administrator'); data=body()
        if audit.status in ('Approved','Completed'): raise ApiError('Reopen audit to change reviewed requirements',409)
        if g.user.id!=audit.reviewer_id or g.user.id==audit.assigned_auditor_id: raise ApiError('Assigned independent reviewer required',403)
        if not str(data.get('comment','')).strip(): raise ApiError('Review rationale required')
        if not Mapping.query.filter_by(requirement_id=id).count(): raise ApiError('No mapped sources to review',409)
        req.status='Complete' if data.get('approve') is True else 'Requires Manual Review'; commit('review requirement','requirement',id,{'comment':data['comment'],'status':req.status}); return jsonify(req.json())

    @app.post('/api/verification/run/<int:id>')
    @authenticated
    def verify_run(id):
        access(id,True); results=verify(id); commit('verify','audit',id); return jsonify(items=results)
    @app.get('/api/verification/results/<int:id>')
    @authenticated
    def verify_results(id): access(id); return paginated(Verification.query.filter_by(audit_id=id))
    @app.get('/api/verification/<int:id>')
    @authenticated
    def verification_detail(id):
        result=db.session.get(Verification,id)
        if not result: raise ApiError('Check not found',404)
        access(result.audit_id); return jsonify(result.json())
    @app.post('/api/reconciliation/run/<int:id>')
    @authenticated
    def reconcile_run(id): access(id,True); results=reconcile(id); commit('reconcile','audit',id); return jsonify(items=results)
    @app.get('/api/reconciliation/results/<int:id>')
    @authenticated
    def reconciliation_results(id): access(id); return paginated(Reconciliation.query.filter_by(audit_id=id))
    @app.get('/api/anomalies/<int:id>')
    @authenticated
    def anomaly_results(id): access(id); return jsonify(anomalies(id))
    @app.post('/api/agents/run/<int:id>')
    @authenticated
    def agents_run(id):
        access(id,True); results=run(id); commit('run workflow','audit',id,{'run_id':results['run_id']}); return jsonify(results)
    @app.get('/api/agents/logs/<int:id>')
    @app.get('/api/agents/status/<int:id>')
    @authenticated
    def agents_logs(id): access(id); return paginated(AgentLog.query.filter_by(audit_id=id))

    @app.get('/api/findings/<int:id>')
    @authenticated
    def findings(id): access(id); return paginated(Finding.query.filter_by(audit_id=id))
    @app.post('/api/findings')
    @authenticated
    def create_finding():
        data=body(); audit=access(int(data.get('audit_id',0)),True)
        title=str(data.get('finding_title','')).strip(); description=str(data.get('description','')).strip()
        if not title or not description: raise ApiError('Title and observation required')
        refs=data.get('evidence_references',[])
        for ref in refs:
            doc=scoped_doc(int(ref.get('document_id',0)))
            if doc.audit_id!=audit.id: raise ApiError('Invalid source audit')
        severity=data.get('severity','Medium')
        if severity not in ('Low','Medium','High','Critical'): raise ApiError('Invalid severity')
        finding=Finding(audit_id=audit.id,finding_title=title[:200],description=description[:10000],severity=severity,evidence_references=refs,recommendation=str(data.get('recommendation','Review supporting evidence.'))[:5000]); db.session.add(finding); invalidate(audit); db.session.flush(); commit('create finding','finding',finding.id); return jsonify(finding.json()),201
    @app.put('/api/findings/<int:id>')
    @authenticated
    def edit_finding(id):
        finding=db.session.get(Finding,id)
        if not finding: raise ApiError('Finding not found',404)
        access(finding.audit_id,True); data=body(); comment=str(data.get('comment','')).strip()
        if not comment: raise ApiError('Comment required')
        status=data.get('status','Pending Review')
        if status not in ('Open','Under Investigation','Pending Review'): raise ApiError('Reviewer action required for final status')
        finding.status=status; finding.reviewer_id=None; finding.reviewer_comments=None; db.session.add(Comment(audit_id=finding.audit_id,finding_id=id,user_id=g.user.id,comment=comment)); commit('update finding','finding',id,{'status':status}); return jsonify(finding.json())
    @app.post('/api/findings/<int:id>/review')
    @authenticated
    def review_finding(id):
        finding=db.session.get(Finding,id)
        if not finding: raise ApiError('Finding not found',404)
        audit=access(finding.audit_id); role('reviewer','administrator'); data=body()
        if audit.status in ('Approved','Completed'): raise ApiError('Reopen audit to change approved findings',409)
        if g.user.id!=audit.reviewer_id or g.user.id==audit.assigned_auditor_id: raise ApiError('Assigned independent reviewer required',403)
        status=data.get('status'); comment=str(data.get('comment','')).strip()
        if status not in ('Accepted','Rejected','Resolved','Under Investigation') or not comment: raise ApiError('Valid decision and rationale required')
        finding.status=status; finding.reviewer_comments=comment; finding.reviewer_id=g.user.id; db.session.add(Comment(audit_id=audit.id,finding_id=id,user_id=g.user.id,comment=comment)); commit('review finding','finding',id,{'status':status,'comment':comment}); return jsonify(finding.json())
    @app.get('/api/findings/<int:id>/comments')
    @authenticated
    def finding_comments(id):
        finding=db.session.get(Finding,id)
        if not finding: raise ApiError('Finding not found',404)
        access(finding.audit_id); return paginated(Comment.query.filter_by(finding_id=id))

    @app.get('/api/dashboard/summary')
    @app.get('/api/dashboard/audit-progress')
    @app.get('/api/dashboard/verification-stats')
    @authenticated
    def dashboard():
        audits=visible().all(); ids=[a.id for a in audits]; docs=Document.query.filter(Document.audit_id.in_(ids),Document.archived.is_(False)).all(); checks=Verification.query.filter(Verification.audit_id.in_(ids)).all(); reqs=Requirement.query.filter(Requirement.audit_id.in_(ids)).all(); finds=Finding.query.filter(Finding.audit_id.in_(ids)).all()
        return jsonify(projects=len(audits),documents=len(docs),processed=sum(d.processing_status=='Processed' for d in docs),pending=sum(d.processing_status!='Processed' for d in docs),requirements=len(reqs),complete=sum(r.status=='Complete' for r in reqs),missing=sum(r.status in ('Missing','Partially Complete') for r in reqs),verified=sum(c.verification_status=='Verified by Rule' for c in checks),discrepancies=sum(c.verification_status=='Discrepancy Detected' for c in checks),manual_review=sum(c.verification_status in ('Requires Human Review','Incomplete','Not Verifiable') for c in checks),completed=sum(a.status=='Completed' for a in audits),categories=dict(Counter(d.document_type for d in docs)),verification=dict(Counter(c.verification_status for c in checks)),uploads=dict(Counter(d.created_at[:7] for d in docs)),findings_over_time=dict(Counter(f.created_at[:10] for f in finds)),discrepancies_by_type=dict(Counter(c.verification_type for c in checks if c.verification_status=='Discrepancy Detected')),audit_progress=[{'id':a.id,'name':a.project_name,'status':a.status,'documents':sum(d.audit_id==a.id for d in docs),'requirements':sum(r.audit_id==a.id for r in reqs),'complete':sum(r.audit_id==a.id and r.status=='Complete' for r in reqs)} for a in audits])
    @app.post('/api/reports/generate/<int:id>')
    @authenticated
    def generate_report(id):
        audit=access(id); data=body(); fmt=data.get('format','pdf')
        if fmt not in ('pdf','xlsx'): raise ApiError('Choose pdf or xlsx')
        report=Report(audit_id=id,format=fmt,snapshot=snapshot(id),approved_by=audit.reviewer_id if audit.status in ('Approved','Completed') else None); db.session.add(report); db.session.flush(); commit('generate report','report',report.id); return jsonify(report.json()),201
    @app.get('/api/reports/<int:id>/download')
    @authenticated
    def report_download(id):
        report=db.session.get(Report,id)
        if not report: raise ApiError('Report not found',404)
        access(report.audit_id); data=pdf_bytes(report) if report.format=='pdf' else xlsx_bytes(report); commit('download','report',id); return send_file(io.BytesIO(data),as_attachment=True,download_name=f'auditflow-{report.audit_id}-{id}.{report.format}',mimetype='application/pdf' if report.format=='pdf' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    @app.get('/api/reports')
    @authenticated
    def reports():
        ids=[a.id for a in visible()]; query=Report.query.filter(Report.audit_id.in_(ids))
        if request.args.get('audit_id'): access(int(request.args['audit_id'])); query=query.filter_by(audit_id=int(request.args['audit_id']))
        return paginated(query)
    @app.get('/api/notifications')
    @authenticated
    def notifications(): return paginated(Notification.query.filter_by(user_id=g.user.id))
    @app.put('/api/notifications/<int:id>/read')
    @authenticated
    def notification_read(id):
        item=db.session.get(Notification,id)
        if not item or item.user_id!=g.user.id: raise ApiError('Notification not found',404)
        item.is_read=True; db.session.commit(); return jsonify(item.json())
    @app.get('/api/audit-logs')
    @authenticated
    def logs():
        role('administrator'); return paginated(AuditLog.query)
    @app.get('/api/settings')
    @authenticated
    def settings(): return jsonify(categories=CATEGORIES,demo_mode=app.config['DEMO_MODE'],retrieval='FAISS local hashing + keyword hybrid',llm_enabled=bool(os.getenv('ANTHROPIC_API_KEY') and os.getenv('LLM_MODEL')),ocr='Tesseract (external executable required)',malware_scan='Configured' if app.config.get('MALWARE_SCANNER') else 'Not configured',max_upload_mb=app.config['MAX_FILE_BYTES']//1024//1024)
    @app.get('/api/contracts')
    def contracts(): return jsonify(endpoints=[{'path':r.rule,'methods':sorted(r.methods-{'HEAD','OPTIONS'})} for r in app.url_map.iter_rules() if r.rule.startswith('/api/')])
    @app.get('/')
    @app.get('/<path:path>')
    def frontend(path=''):
        if path.startswith('api/'): raise ApiError('API endpoint not found',404)
        folder=ROOT/'frontend'/'dist'
        if (folder/path).is_file(): return send_from_directory(folder,path)
        if (folder/'index.html').exists(): return send_from_directory(folder,'index.html')
        return jsonify(message='API is running. Start the Vite frontend or build frontend/dist.'),200
    @app.cli.command('init-db')
    def init_db():
        from .migrate import upgrade
        upgrade(); print('Database initialized.')
    @app.cli.command('seed-demo')
    def seed_demo():
        from .seed import seed
        seed(); print('Synthetic demonstration data initialized.')
    @app.cli.command('create-user')
    @click.option('--email',required=True)
    @click.option('--username',required=True)
    @click.option('--role',type=click.Choice(['auditor','reviewer','administrator']),required=True)
    def create_user_command(email,username,role):
        from .provision import create_user
        create_user(email,username,role); print('User provisioned.')
    return app
