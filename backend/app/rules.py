"""Deterministic financial checks. Values remain Decimal throughout."""
from collections import defaultdict
from datetime import date
from decimal import Decimal
from .models import db, Document, Record, Verification, Reconciliation, Finding, Audit
from .processing import money

def active_records(audit_id):
    docs={d.id:d for d in Document.query.filter_by(audit_id=audit_id,archived=False,processing_status='Processed')}
    return [(docs[r.document_id],r) for r in Record.query.filter(Record.document_id.in_(docs)).all()] if docs else []
def ref(doc,row): return {'document_id':doc.id,'document_name':doc.document_name,'version':doc.file_version,'section':row.source_reference}
def amount(values): return money(values.get('amount',values.get('total','0')))
def parsed_date(value):
    try: return date.fromisoformat(str(value)[:10])
    except (ValueError,TypeError): return None

def verify(audit_id):
    audit=db.session.get(Audit,audit_id); settings=audit.settings or {}; tolerance=money(settings.get('tolerance','0.01')); disabled=set(settings.get('disabled_rules',[]))
    Verification.query.filter_by(audit_id=audit_id).delete(); rows=active_records(audit_id); seen={}
    def emit(kind,doc,row,status,explanation,expected=None,actual=None,other=None):
        if kind in disabled: return
        sources=[ref(doc,row)]+([other] if other else [])
        db.session.add(Verification(audit_id=audit_id,verification_type=kind,source_document_id=doc.id,comparison_document_id=other['document_id'] if other else None,expected_value=expected,actual_value=actual,difference=actual-expected if actual is not None and expected is not None else None,verification_status=status,explanation=explanation,evidence_references=sources))
    for doc,row in rows:
        v=row.values; category=doc.document_type
        dt=parsed_date(v.get('date'))
        emit('Period validation',doc,row,'Incomplete' if not dt else 'Verified by Rule' if audit.audit_period_start<=dt.isoformat()<=audit.audit_period_end else 'Discrepancy Detected','Date is missing/invalid.' if not dt else f'Transaction date {dt} checked against {audit.audit_period_start} to {audit.audit_period_end}.')
        if category in ('Purchase invoices','Sales invoices'):
            missing=[k for k in ['invoice_number','date','currency','amount','vendor' if category=='Purchase invoices' else 'customer'] if not v.get(k)]
            emit('Invoice required fields',doc,row,'Incomplete' if missing else 'Verified by Rule','Missing: '+', '.join(missing) if missing else 'Required invoice fields are present; authenticity was not assessed.')
            if 'amount' in v: emit('Invoice amount',doc,row,'Verified by Rule' if money(v['amount'])>=0 else 'Requires Human Review','Amount sign checked; negative amounts may be credit notes.',Decimal('0'),money(v['amount']))
            if all(k in v for k in ('net','tax','total')):
                expected=money(v['net'])+money(v['tax']); actual=money(v['total'])
                emit('Invoice tax arithmetic',doc,row,'Verified by Rule' if abs(actual-expected)<=tolerance else 'Discrepancy Detected','Net plus tax compared to total. Tax rate applicability is not assessed.',expected,actual)
            else: emit('Invoice tax arithmetic',doc,row,'Not Verifiable','net, tax and total are required to check arithmetic.')
            key=(category,v.get('vendor',v.get('customer')),v.get('invoice_number'),v.get('currency'))
            if v.get('invoice_number'):
                if key in seen: emit('Duplicate invoice',doc,row,'Discrepancy Detected','Same counterparty, currency and invoice number already occur.',other=seen[key])
                else: seen[key]=ref(doc,row)
        if category in ('General ledger','Trial balance','Journal entries'):
            emit('Ledger required fields',doc,row,'Verified by Rule' if all(k in v for k in ('account_code','reference','date')) else 'Incomplete','Account code, reference and date presence checked.')
            if 'debit' in v and 'credit' in v: emit('Ledger amount signs',doc,row,'Verified by Rule' if money(v['debit'])>=0 and money(v['credit'])>=0 else 'Discrepancy Detected','Debit and credit checked for nonnegative values.')
        if category=='Bank statements':
            if 'debit' in v and 'credit' in v:
                debit=money(v['debit']);credit=money(v['credit'])
                emit('Bank amount signs',doc,row,'Discrepancy Detected' if debit<0 or credit<0 else 'Requires Human Review' if debit and credit else 'Verified by Rule','Debit/credit sign and simultaneous debit/credit presence checked.')
            emit('Bank reference',doc,row,'Verified by Rule' if v.get('reference') else 'Incomplete','Transaction reference presence checked.')
            if all(k in v for k in ('opening_balance','closing_balance','debit','credit')):
                expected=money(v['opening_balance'])+money(v['credit'])-money(v['debit']); actual=money(v['closing_balance'])
                emit('Bank balance arithmetic',doc,row,'Verified by Rule' if abs(expected-actual)<=tolerance else 'Discrepancy Detected','Opening + credit - debit compared with closing; bank sign convention must be reviewed.',expected,actual)
            else: emit('Bank balance arithmetic',doc,row,'Not Verifiable','Opening/closing balance and debit/credit fields are required.')
        if category=='Payroll documents':
            employee=v.get('employee_id');key=('payroll',employee,v.get('date'),v.get('amount'),v.get('currency'))
            if employee and key in seen:emit('Duplicate employee payment',doc,row,'Discrepancy Detected','Employee, date, amount and currency repeat in payroll records.',other=seen[key])
            elif employee:seen[key]=ref(doc,row)
            employee_source=next(((d,r) for d,r in rows if d.document_type=='Other supporting documents' and employee and r.values.get('employee_id')==employee),None)
            emit('Employee record matching',doc,row,'Requires Human Review' if employee_source else 'Incomplete','Employee ID matches a supporting register; employment validity requires review.' if employee_source else 'No supporting employee register row found.',other=ref(*employee_source) if employee_source else None)
            if all(k in v for k in ('employee_id','salary','deductions','amount')):
                expected=money(v['salary'])-money(v['deductions']); actual=money(v['amount'])
                emit('Payroll net pay',doc,row,'Verified by Rule' if abs(expected-actual)<=tolerance else 'Discrepancy Detected','Salary minus deductions compared with paid amount.',expected,actual)
            else: emit('Payroll net pay',doc,row,'Incomplete','Employee ID, salary, deductions and amount are required.')
        if category=='Expense reports':
            expense_key=('expense',v.get('reference'),v.get('date'),v.get('amount'),v.get('currency'))
            if v.get('reference') and expense_key in seen:emit('Duplicate expense claim',doc,row,'Discrepancy Detected','Expense reference, date, amount and currency repeat.',other=seen[expense_key])
            elif v.get('reference'):seen[expense_key]=ref(doc,row)
            match=next(((d,r) for d,r in rows if d.document_type=='Payment receipts' and v.get('reference') and r.values.get('reference')==v['reference'] and r.values.get('currency')==v.get('currency')),None)
            emit('Expense receipt',doc,row,'Requires Human Review' if match else 'Incomplete','A receipt reference matches; review its nature and amount.' if match else 'No matching receipt reference and currency located.',other=ref(*match) if match else None)
            if match and 'amount' in v and 'amount' in match[1].values:
                expected=money(v['amount']);actual=money(match[1].values['amount'])
                emit('Expense receipt amount',doc,row,'Verified by Rule' if abs(expected-actual)<=tolerance else 'Discrepancy Detected','Expense claim compared with referenced receipt amount.',expected,actual,ref(*match))
    # Double entry balancing is across each journal reference and currency, not each line.
    groups=defaultdict(list)
    for doc,row in rows:
        if doc.document_type in ('General ledger','Trial balance','Journal entries') and row.values.get('currency') and 'debit' in row.values and 'credit' in row.values: groups[(doc.id,row.values.get('reference'),row.values['currency'])].append((doc,row))
    for key,group in groups.items():
        debit=sum((money(r.values['debit']) for _,r in group),Decimal(0)); credit=sum((money(r.values['credit']) for _,r in group),Decimal(0))
        emit('Ledger balance',*group[0],'Verified by Rule' if abs(debit-credit)<=tolerance else 'Discrepancy Detected',f'Debits and credits aggregated for reference {key[1]} in {key[2]}.',debit,credit)
    for doc in Document.query.filter_by(audit_id=audit_id,archived=False,processing_status='Processed'):
        if not any(d.id==doc.id for d,_ in rows):
            db.session.add(Verification(audit_id=audit_id,verification_type='Structured data availability',source_document_id=doc.id,verification_status='Not Verifiable',explanation='No normalized financial rows were extracted. Review text or supply structured CSV/XLSX records.',evidence_references=[{'document_id':doc.id,'version':doc.file_version,'section':'Document'}]))
    db.session.flush(); return [v.json() for v in Verification.query.filter_by(audit_id=audit_id)]

PAIRS=[('Bank statements','Cash book'),('General ledger','Trial balance'),('Purchase register','Purchase invoices'),('Sales register','Sales invoices'),('Payroll documents','Payment receipts'),('Expense register','Payment receipts'),('Purchase invoices','Payment receipts'),('Sales invoices','Payment receipts'),('Purchase orders','Purchase invoices'),('Purchase invoices','Goods received notes')]
def reconcile(audit_id):
    settings=db.session.get(Audit,audit_id).settings or {}; tolerance=money(settings.get('tolerance','0.01')); window=int(settings.get('date_window',7)); rows=active_records(audit_id)
    Reconciliation.query.filter_by(audit_id=audit_id).delete()
    for left,right in PAIRS:
        sources=[(d,r) for d,r in rows if d.document_type==left]; targets=[(d,r) for d,r in rows if d.document_type==right]; used=set()
        if not sources: continue
        for doc,row in sources:
            v=row.values; currency=v.get('currency'); reference=v.get('reference') or v.get('invoice_number'); dt=parsed_date(v.get('date')); expected=amount(v) if 'amount' in v or 'total' in v else None
            candidates=[]
            for d,r in targets:
                other=r.values; od=parsed_date(other.get('date'))
                if r.id in used or not currency or currency!=other.get('currency') or not dt or not od or abs((dt-od).days)>window: continue
                exact_ref=reference and reference==(other.get('reference') or other.get('invoice_number'))
                if expected is None or not ('amount' in other or 'total' in other): continue
                delta=abs(expected-amount(other))
                if exact_ref or delta<=tolerance: candidates.append((0 if exact_ref else 1,delta,d,r))
            candidates.sort(key=lambda item:(item[0],item[1],item[3].id)); matched=candidates[0] if candidates else None
            ambiguous=matched and len(candidates)>1 and candidates[1][:2]==matched[:2]
            actual=None; matched_ref=None
            if matched and not ambiguous:
                _,_,md,mr=matched; used.add(mr.id); actual=amount(mr.values); matched_ref=ref(md,mr)
            status='Requires Human Review' if ambiguous else 'Incomplete' if expected is None or not currency or not dt else 'Unmatched' if actual is None else 'Verified by Rule' if abs(actual-expected)<=tolerance else 'Discrepancy Detected'
            db.session.add(Reconciliation(audit_id=audit_id,record_type=f'{left} / {right}',source_reference=ref(doc,row),matched_reference=matched_ref,expected_amount=expected,actual_amount=actual,difference=actual-expected if actual is not None else None,currency=currency,status=status))
        for doc,row in targets:
            if row.id not in used: db.session.add(Reconciliation(audit_id=audit_id,record_type=f'{left} / {right}',source_reference=None,matched_reference=ref(doc,row),actual_amount=amount(row.values) if 'amount' in row.values or 'total' in row.values else None,currency=row.values.get('currency'),status='Unmatched'))
    db.session.flush(); return [x.json() for x in Reconciliation.query.filter_by(audit_id=audit_id)]

def anomalies(audit_id):
    from sklearn.ensemble import IsolationForest
    rows=active_records(audit_id); results=[]; groups=defaultdict(list); seen={}
    for doc,row in rows:
        v=row.values
        if 'amount' not in v or not v.get('currency'): continue
        groups[v['currency']].append((doc,row))
        key=(v.get('reference'),v.get('date'),v['amount'],v['currency'],doc.document_type)
        if v.get('reference') and key in seen: results.append({'kind':'Duplicate transaction indicator','source':ref(doc,row),'comparison':seen[key],'explanation':'Same reference, date, currency, amount and category. This may have a legitimate explanation; review required.'})
        seen[key]=ref(doc,row)
    for currency,group in groups.items():
        if len(group)<8: continue
        values=[[float(amount(r.values))] for _,r in group]; model=IsolationForest(contamination='auto',random_state=42,n_estimators=100); labels=model.fit_predict(values); scores=model.decision_function(values)
        for (doc,row),label,score in zip(group,labels,scores):
            if label==-1: results.append({'kind':'Unusual amount indicator','source':ref(doc,row),'amount':str(amount(row.values)),'currency':currency,'score':round(float(score),4),'explanation':f'Isolation Forest flagged an amount relative to {len(group)} same-currency rows. Not evidence of fraud.'})
    return {'indicators':results,'method':'IsolationForest; one-dimensional amount per currency, random_state=42, minimum 8 rows. Deterministic duplicate reference checks.','sample_count':sum(len(g) for g in groups.values())}
