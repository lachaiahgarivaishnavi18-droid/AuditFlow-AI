import io,zipfile
from decimal import Decimal
from pathlib import Path
import pytest
from app.models import db,Document,Record,Verification,Chunk,Requirement,Report,Audit,Finding
from app.processing import money,unpack,vector,normalize,extract,classify

def upload(client,headers,audit,text,name='invoice.csv',category='Purchase invoices'):
    return client.post('/api/documents/upload',headers=headers,data={'audit_id':str(audit),'category':category,'files':(io.BytesIO(text.encode()),name)},content_type='multipart/form-data')
def login(client,email): return {'Authorization':'Bearer '+client.post('/api/auth/login',json={'email':email,'password':'TestPassword!2026'}).json['token']}

def test_auth_revocation_and_registration(client,headers):
    assert client.get('/api/auth/me').status_code==401
    assert client.get('/api/auth/me',headers=headers).status_code==200
    assert client.post('/api/auth/register',json={'username':'New auditor','email':'new@test.com','password':'TestPassword!2026','role':'administrator'}).json['user']['role']=='auditor'
    assert client.post('/api/auth/logout',headers=headers).status_code==200
    assert client.get('/api/auth/me',headers=headers).status_code==401

def test_project_isolation(client,headers,audit):
    other=login(client,'other@test.com')
    assert client.get(f'/api/audits/{audit}',headers=other).status_code==403
    assert client.get('/api/audits',headers=other).json['total']==0
    assert client.post('/api/rag/query',headers=other,json={'audit_id':audit,'query':'invoice'}).status_code==403
    assert client.post('/api/agents/run/'+str(audit),headers=other).status_code==403
    assert client.post('/api/audits',headers=login(client,'reviewer@test.com'),json={}).status_code==403

def test_upload_versions_citations_and_archive(client,headers,audit):
    text='reference,date,invoice_number,vendor,amount,currency\nI-1,2026-03-01,I-1,Atlas,50000,INR\n'
    response=upload(client,headers,audit,text); assert response.status_code==201,response.json
    doc=response.json['items'][0]; assert doc['processing_status']=='Processed'
    result=client.post('/api/rag/query',headers=headers,json={'audit_id':audit,'query':'Atlas invoice'}).json
    assert result['sources'][0]['document_id']==doc['id'];assert 'CSV' in result['sources'][0]['section_reference'];assert result['sources'][0]['version']==1
    other=login(client,'other@test.com');assert client.get(f"/api/documents/{doc['id']}/download",headers=other).status_code==403
    second=upload(client,headers,audit,text).json['items'][0];assert second['file_version']==2;assert second['previous_version_id']==doc['id']
    assert client.get(f"/api/documents/{doc['id']}",headers=headers).json['archived'] is True
    assert client.get(f"/api/documents/{doc['id']}/download",headers=headers).data==text.encode()
    assert client.post('/api/rag/query',headers=headers,json={'audit_id':audit,'query':'nonexistentzebra'}).json['sources']==[]

def test_rules_and_decimal_reconciliation(client,headers,audit,app):
    invoice='reference,date,invoice_number,vendor,amount,currency,net,tax,total\nINV-1,2026-03-01,INV-1,Atlas,50000,INR,45000,5000,50000\nINV-1,2026-03-01,INV-1,Atlas,50000,INR,45000,5000,50000\nINV-2,2026-03-02,INV-2,,100,INR,90,9,100\n'
    upload(client,headers,audit,invoice)
    results=client.post(f'/api/verification/run/{audit}',headers=headers).json['items']
    assert any(r['verification_type']=='Duplicate invoice' and r['verification_status']=='Discrepancy Detected' for r in results)
    assert any(r['verification_type']=='Invoice required fields' and r['verification_status']=='Incomplete' for r in results)
    assert any(r['verification_type']=='Invoice tax arithmetic' and Decimal(r['difference'] or 0)==1 for r in results)
    upload(client,headers,audit,'reference,date,amount,currency\nB1,2026-03-01,50000,INR\nB2,2026-03-02,0.30,INR\n','bank.csv','Bank statements')
    upload(client,headers,audit,'reference,date,amount,currency\nB1,2026-03-01,45000,INR\nB2,2026-03-02,0.30,INR\n','cash.csv','Cash book')
    result=client.post(f'/api/reconciliation/run/{audit}',headers=headers).json['items']; records=[r for r in result if r['record_type']=='Bank statements / Cash book']
    assert any(Decimal(r['difference'] or 0)==-5000 and r['status']=='Discrepancy Detected' for r in records)
    assert any(r['status']=='Verified by Rule' and Decimal(r['difference'])==0 for r in records)
    assert money('0.1')+money('0.2')==Decimal('0.3')
    for value in ['NaN','Infinity','1e99','0.000001']:
        with pytest.raises(ValueError): money(value)

def test_zip_safety_and_processing_errors(client,headers,audit):
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w') as archive: archive.writestr('../escape.txt','bad')
    with pytest.raises(ValueError):unpack(output.getvalue())
    response=upload(client,headers,audit,'not a PDF','broken.pdf','Bank statements')
    assert response.json['items'][0]['processing_status']=='Failed'
    result=client.post(f'/api/agents/run/{audit}',headers=headers)
    assert result.status_code==200,result.json
    assert result.json['failed'] is True
    logs=client.get(f'/api/agents/logs/{audit}',headers=headers).json['items']
    assert any(r['agent_name']=='Extraction remediation' for r in logs)
    assert not any(r['agent_name']=='Evidence Verification Agent' for r in logs)

def test_mapping_workflow_and_reports(client,headers,audit,app):
    upload(client,headers,audit,'reference,date,invoice_number,vendor,amount,currency\nI1,2026-03-01,I1,Atlas,100,INR\n')
    result=client.post(f'/api/agents/run/{audit}',headers=headers);assert result.status_code==200,result.json
    assert result.json['awaiting_review'] is True
    logs=client.get(f'/api/agents/logs/{audit}',headers=headers).json['items'];assert len(logs)==8;assert all(r['output_summary'] for r in logs)
    mapping=client.get(f'/api/evidence/{audit}',headers=headers).json;assert mapping['requests'];assert mapping['mappings'];assert mapping['complete']==0
    assert client.post(f'/api/audits/{audit}/approve',headers=headers,json={'comment':'Approve'}).status_code==403
    reviewer=login(client,'reviewer@test.com')
    assert client.post(f'/api/audits/{audit}/approve',headers=reviewer,json={'comment':'Approve'}).status_code==409
    for fmt in ('pdf','xlsx'):
        response=client.post(f'/api/reports/generate/{audit}',headers=headers,json={'format':fmt});assert response.status_code==201,response.json
        report=response.json;assert report['approved_by'] is None
        download=client.get(f"/api/reports/{report['id']}/download",headers=headers);assert download.status_code==200
        assert download.data.startswith(b'%PDF' if fmt=='pdf' else b'PK')
        assert client.get(f"/api/reports/{report['id']}/download",headers=login(client,'other@test.com')).status_code==403
        if fmt=='xlsx':
            from openpyxl import load_workbook
            workbook=load_workbook(io.BytesIO(download.data));assert len(workbook.sheetnames)==7

def test_actual_pdf_docx_excel_extraction(tmp_path,app):
    from reportlab.pdfgen import canvas
    from openpyxl import Workbook
    from docx import Document as Word
    pdf=tmp_path/'source.pdf';c=canvas.Canvas(str(pdf));c.drawString(40,800,'SYNTHETIC Invoice Atlas INR 50000');c.save()
    word=tmp_path/'source.docx';d=Word();d.add_paragraph('SYNTHETIC Invoice number: INV-001');d.save(word)
    xlsx=tmp_path/'source.xlsx';w=Workbook();w.active.title='Ledger';w.active.append(['reference','amount','currency']);w.active.append(['A1',50000,'INR']);w.save(xlsx)
    with app.app_context():
        units,rows,method=extract(pdf);assert 'Atlas' in units[0][2];assert units[0][0]==1
        units,rows,method=extract(word);assert 'INV-001' in units[0][2]
        units,rows,method=extract(xlsx);assert rows[0][1]['amount']=='50000';assert rows[0][0]=='Ledger row 2'
    assert classify('bank.csv','')=='Bank statements';assert vector('invoice bank')==vector('invoice bank')
    assert normalize({'Invoice No':'A','Total Amount':'1,200.01'})=={'invoice_number':'A','total':'1200.01'}

def test_ocr_path_failure_is_visible(tmp_path,app,monkeypatch):
    from PIL import Image
    import app.processing as processing
    path=tmp_path/'scan.png';Image.new('RGB',(200,100),'white').save(path)
    monkeypatch.setattr(processing,'ocr',lambda image:'SYNTHETIC bank statement reference A1')
    with app.app_context():
        units,rows,method=extract(path);assert method=='OCR';assert units[0][0]==1;assert 'A1' in units[0][2]

def test_dashboard_is_database_driven(client,headers,audit):
    before=client.get('/api/dashboard/summary',headers=headers).json
    upload(client,headers,audit,'reference,date,amount,currency\nA,2026-03-01,100,INR\n')
    after=client.get('/api/dashboard/summary',headers=headers).json
    assert after['projects']==1;assert after['documents']==before['documents']+1;assert after['processed']==1

def test_independent_review_and_approval_freeze(client,headers,audit,app):
    reviewer=login(client,'reviewer@test.com')
    with app.app_context():
        audit_obj=db.session.get(Audit,audit);audit_obj.status='Under Review'
        reqs=Requirement.query.filter_by(audit_id=audit).all()
        for req in reqs:req.status='Complete'
        finding=Finding(audit_id=audit,finding_title='Human review',description='SYNTHETIC observation',evidence_references=[]);db.session.add(finding);db.session.commit();fid=finding.id
    assert client.post(f'/api/findings/{fid}/review',headers=headers,json={'status':'Accepted','comment':'test'}).status_code==403
    assert client.post(f'/api/findings/{fid}/review',headers=reviewer,json={'status':'Accepted','comment':'Source inspected'}).status_code==200
    assert client.post(f'/api/audits/{audit}/approve',headers=reviewer,json={'comment':'Reviewed all evidence'}).status_code==200
    assert upload(client,headers,audit,'text','new.txt').status_code==409
    report=client.post(f'/api/reports/generate/{audit}',headers=headers,json={'format':'pdf'}).json;assert report['approved_by']==3

def test_currency_and_date_boundaries(client,headers,audit):
    upload(client,headers,audit,'reference,date,amount,currency\nA1,2026-03-01,100,INR\n','bank.csv','Bank statements')
    upload(client,headers,audit,'reference,date,amount,currency\nA1,2026-03-01,100,USD\nA1,2026-03-31,100,INR\n','cash.csv','Cash book')
    rows=client.post(f'/api/reconciliation/run/{audit}',headers=headers).json['items'];assert all(r['status']=='Unmatched' for r in rows)

def test_anomaly_detection_is_repeatable(client,headers,audit):
    text='reference,date,amount,currency\n'+'\n'.join(f'A{i},2026-03-01,{100+i if i<15 else 1000000},INR' for i in range(16))
    upload(client,headers,audit,text,'transactions.csv','Journal entries')
    first=client.get(f'/api/anomalies/{audit}',headers=headers).json;second=client.get(f'/api/anomalies/{audit}',headers=headers).json
    assert first==second;assert first['sample_count']==16;assert first['indicators']

def test_money_storage_preserves_precision(app):
    with app.app_context():
        from app.models import Reconciliation,Organization,Audit
        org=Organization(organization_name='Precision');db.session.add(org);db.session.flush()
        project=Audit(project_name='Precision',organization_id=org.id,assigned_auditor_id=1,financial_year='2026',audit_period_start='2026-01-01',audit_period_end='2026-12-31');db.session.add(project);db.session.flush()
        value=Decimal('12345678901234567890.1234')
        result=Reconciliation(audit_id=project.id,expected_amount=value,actual_amount=value,difference=Decimal('0.0000'));db.session.add(result);db.session.commit();rid=result.id;db.session.expire_all()
        assert db.session.get(Reconciliation,rid).expected_amount==value

def test_optional_llm_quotes_are_validated(app,monkeypatch):
    import json
    import app.llm as llm
    monkeypatch.setenv('ANTHROPIC_API_KEY','test-key');monkeypatch.setenv('LLM_MODEL','test-model')
    class Response:
        def __init__(self,quote):self.quote=quote
        def __enter__(self):return io.BytesIO(json.dumps({'content':[{'type':'text','text':json.dumps({'citations':[{'chunk_id':1,'quote':self.quote}]})}]}).encode())
        def __exit__(self,*args):pass
    monkeypatch.setattr(llm.urllib.request,'urlopen',lambda *a,**k:Response('Atlas 50000'))
    result=llm.select_quotes('Atlas',[{'chunk_id':1,'text':'SYNTHETIC Atlas 50000 INR','document_id':1}]);assert result['sources'][0]['text']=='Atlas 50000'
    monkeypatch.setattr(llm.urllib.request,'urlopen',lambda *a,**k:Response('Invented 99999'))
    with pytest.raises(ValueError):llm.select_quotes('Atlas',[{'chunk_id':1,'text':'Atlas 50000','document_id':1}])

def test_assistant_financial_tools_and_invalidation(client,headers,audit):
    text='reference,date,invoice_number,vendor,amount,currency\nI1,2026-03-01,I1,Atlas,150000,INR\nI1,2026-03-01,I1,Atlas,150000,INR\nI2,2026-03-02,I2,Atlas,100,INR\n'
    upload(client,headers,audit,text)
    result=client.post('/api/rag/query',headers=headers,json={'audit_id':audit,'query':'Show invoices above ₹1,00,000'}).json
    assert len(result['tool_results'])==2;assert result['sources'];assert result['mode']=='Deterministic backend tool'
    result=client.post('/api/rag/query',headers=headers,json={'audit_id':audit,'query':'Find duplicate invoice numbers'}).json
    assert len(result['tool_results'])==1;assert len(result['tool_results'][0]['evidence_references'])==2
    client.post(f'/api/verification/run/{audit}',headers=headers)
    assert client.get(f'/api/verification/results/{audit}',headers=headers).json['total']>0
    upload(client,headers,audit,'SYNTHETIC new evidence','new.txt','Other supporting documents')
    assert client.get(f'/api/verification/results/{audit}',headers=headers).json['total']==0

def test_semantic_adapter_preserves_vectors(monkeypatch):
    import numpy as np
    import app.embeddings as embeddings
    class Encoder:
        def encode(self,text,normalize_embeddings):
            assert normalize_embeddings is True
            return np.array([0.6,0.8])
    monkeypatch.setenv('EMBEDDING_MODEL','test-local-model')
    monkeypatch.setattr(embeddings,'encoder',lambda name:Encoder())
    assert vector('bank receipt')=={'0':0.6,'1':0.8}

def test_agent_exception_routes_to_remediation(client,headers,audit,monkeypatch):
    import app.workflow as workflow
    def failing(_):raise AssertionError()
    nodes=list(workflow.NODES);nodes[2]=(nodes[2][0],failing);monkeypatch.setattr(workflow,'NODES',nodes)
    result=client.post(f'/api/agents/run/{audit}',headers=headers)
    assert result.status_code==200,result.json
    assert result.json['failed'] is True
    logs=client.get(f'/api/agents/logs/{audit}',headers=headers).json['items']
    assert any(r['error_message']=='AssertionError: ' for r in logs)

def test_custom_column_mapping_is_preserved(client,headers,audit):
    response=client.post('/api/documents/upload',headers=headers,data={'audit_id':str(audit),'category':'Bank statements','column_mapping':'{"Voucher":"reference","Value":"amount","Unit":"currency"}','files':(io.BytesIO(b'Voucher,Value,Unit,date\nV1,100.01,INR,2026-03-01\n'),'custom.csv')},content_type='multipart/form-data')
    assert response.status_code==201,response.json
    doc=response.json['items'][0];assert doc['processing_status']=='Processed'
    values=client.get(f"/api/documents/{doc['id']}/extracted-text",headers=headers).json['records'][0]['values']
    assert values['reference']=='V1';assert values['amount']=='100.01'
    assert doc['metadata_json']['column_mapping']['Voucher']=='reference'

def test_durable_original_survives_missing_local_file(client,headers,audit,app):
    app.config['STORE_ORIGINALS_IN_DB']=True
    content='SYNTHETIC evidence bank record A123'
    response=upload(client,headers,audit,content,'persistent.txt','Bank statements')
    doc=response.json['items'][0];assert doc['processing_status']=='Processed'
    with app.app_context():
        original=db.session.get(Document,doc['id']);Path(original.file_path).unlink()
        original.file_path='C:\\different-machine\\missing\\original.txt';db.session.commit()
    result=client.get(f"/api/documents/{doc['id']}/download",headers=headers)
    assert result.data==content.encode()
    result=client.post(f"/api/rag/index/{doc['id']}",headers=headers)
    assert result.status_code==200;assert result.json['processing_status']=='Processed'
    with app.app_context():assert Path(db.session.get(Document,doc['id']).file_path).exists()
