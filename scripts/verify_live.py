"""Smoke-test the deployed synthetic demo without printing session credentials."""
import json,sys,urllib.request
base=sys.argv[1].rstrip('/');token=None
def request(path,body=None):
    headers={'Content-Type':'application/json'}
    if token:headers['Authorization']='Bearer '+token
    req=urllib.request.Request(base+'/api'+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
    with urllib.request.urlopen(req,timeout=180) as response:
        content=response.read()
        return json.loads(content) if 'application/json' in response.headers.get('Content-Type','') else content
health=request('/health');assert health['status']=='ok'
auth=request('/auth/login',{'email':'auditor@auditflow.demo','password':'AuditFlowDemo!2026'});token=auth['token']
audits=request('/audits');audit_id=audits['items'][0]['id']
docs=request(f'/documents?audit_id={audit_id}');assert docs['total']>=5
source=request(f"/documents/{docs['items'][0]['id']}/download");assert b'SYNTHETIC' in source
indexed=request(f"/rag/index/{docs['items'][0]['id']}",{});assert indexed['processing_status']=='Processed'
result=request('/rag/query',{'audit_id':audit_id,'query':'Atlas invoice INV-001'});assert result['sources']
workflow=request(f'/agents/run/{audit_id}',{});assert workflow['awaiting_review'] and not workflow['failed']
report=request(f'/reports/generate/{audit_id}',{'format':'pdf'});pdf=request(f"/reports/{report['id']}/download");assert pdf.startswith(b'%PDF')
request('/auth/logout',{})
print({'url':base,'health':'ok','login':'ok','documents':docs['total'],'original_download':'ok','cited_retrieval':'ok','agents':'ok','pdf_report':'ok'})
