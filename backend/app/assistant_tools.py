"""Read-only deterministic audit assistant tools. All factual rows cite evidence."""
import re
from decimal import Decimal
from .models import db,Verification,Requirement,Mapping,Chunk,Document
from .rules import active_records,ref,amount
from .processing import money

def tool_query(audit_id,query):
    lower=query.lower(); rows=active_records(audit_id); result=[]; tool=None
    if 'duplicate' in lower and ('invoice' in lower or 'transaction' in lower):
        tool='Duplicate invoice/transaction key check'; seen={}
        for doc,row in rows:
            v=row.values
            if 'invoice' in lower:
                if doc.document_type not in ('Purchase invoices','Sales invoices') or not v.get('invoice_number'):continue
                key=(doc.document_type,v.get('vendor',v.get('customer')),v['invoice_number'],v.get('currency'))
            else:
                if not v.get('reference'):continue
                key=(doc.document_type,v.get('reference'),v.get('date'),v.get('amount'),v.get('currency'))
            if key in seen:result.append({'observation':'Repeated key; investigate whether this is a duplicate record.','values':v,'evidence_references':[ref(doc,row),seen[key]]})
            else:seen[key]=ref(doc,row)
    elif any(w in lower for w in ('above','over','greater than')) and any(w in lower for w in ('invoice','transaction','journal')):
        match=re.search(r'(?:above|over|greater than)\s*(?:₹|rs\.?|inr|usd|\$)?\s*([\d,]+(?:\.\d{1,4})?)',lower)
        if not match:return None
        threshold=money(match.group(1)); tool=f'Exact amount greater than {threshold}; currencies kept separate'
        for doc,row in rows:
            if 'invoice' in lower and doc.document_type not in ('Purchase invoices','Sales invoices'):continue
            if 'journal' in lower and doc.document_type not in ('Journal entries','General ledger'):continue
            if ('amount' in row.values or 'total' in row.values) and amount(row.values)>threshold:result.append({'observation':'Source amount exceeds the requested threshold.','values':row.values,'evidence_references':[ref(doc,row)]})
    elif 'discrepanc' in lower:
        tool='Stored deterministic verification discrepancies'
        for check in Verification.query.filter_by(audit_id=audit_id,verification_status='Discrepancy Detected'):result.append({'observation':check.explanation,'values':{'expected':str(check.expected_value) if check.expected_value is not None else None,'actual':str(check.actual_value) if check.actual_value is not None else None,'difference':str(check.difference) if check.difference is not None else None},'evidence_references':check.evidence_references})
    elif ('missing' in lower or 'incomplete' in lower) and ('requirement' in lower or 'evidence' in lower):
        tool='Stored evidence requirement coverage'
        for req in Requirement.query.filter_by(audit_id=audit_id).filter(Requirement.status!='Complete'):
            result.append({'observation':f'{req.requirement_name}: {req.status}. Required categories: '+', '.join(req.required_evidence_type),'values':{'requirement_id':req.id,'status':req.status},'evidence_references':[m.source_reference for m in Mapping.query.filter_by(requirement_id=req.id)]})
    if tool is None:return None
    sources=[]; seen=set()
    for item in result:
        for source in item['evidence_references']:
            key=(source.get('document_id'),source.get('section'))
            if key in seen:continue
            seen.add(key);doc=db.session.get(Document,source['document_id'])
            if not doc or doc.audit_id!=audit_id:continue
            chunk=Chunk.query.filter_by(document_id=doc.id).first()
            sources.append({'document_id':doc.id,'document_name':doc.document_name,'version':doc.file_version,'section_reference':source.get('section',source.get('section_reference','Document')),'page_number':source.get('page'),'chunk_id':chunk.id if chunk else -doc.id,'score':1.0,'text':str(item['values']) if item['values'] else item['observation']})
    return {'answer':f'{tool}: {len(result)} result(s). Review the cited source records; these checks do not establish authenticity or fraud.','tool':tool,'tool_results':result,'sources':sources,'mode':'Deterministic backend tool','limitations':'Results are restricted to this audit. Missing records or no detected discrepancies do not establish an absence of audit risk.'}
