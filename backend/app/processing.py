"""Bounded document ingestion. No document content is executable."""
import csv, hashlib, io, json, os, re, subprocess, uuid, zipfile
from pathlib import Path, PurePosixPath
from decimal import Decimal, InvalidOperation
from flask import current_app
from werkzeug.utils import secure_filename
from .models import db, Document, Chunk, Record,DocumentBlob

EXTENSIONS={'.pdf','.docx','.xlsx','.csv','.txt','.jpg','.jpeg','.png'}
CATEGORIES=['Bank statements','General ledger','Trial balance','Purchase invoices','Sales invoices','Payment receipts','Payroll documents','Tax records','Contracts','Expense reports','Financial statements','Journal entries','Cash book','Purchase register','Sales register','Expense register','Goods received notes','Purchase orders','Other supporting documents']
ALIASES={'transaction_reference':'reference','transaction_id':'reference','ref':'reference','invoice_no':'invoice_number','invoice':'invoice_number','transaction_date':'date','vendor_name':'vendor','customer_name':'customer','net_amount':'net','tax_amount':'tax','total_amount':'total','gross_salary':'salary','employee':'employee_id','balance_open':'opening_balance','balance_close':'closing_balance'}
MONEY={'amount','debit','credit','opening_balance','closing_balance','tax','net','total','salary','deductions'}

def money(value):
    value=str(value).strip().replace(',','').replace('₹','').replace('$','')
    if value.startswith('(') and value.endswith(')'): value='-'+value[1:-1]
    try:
        result=Decimal(value)
        if not result.is_finite() or abs(result)>Decimal('99999999999999999999'): raise ValueError('Amount out of range')
        if result.as_tuple().exponent < -4: raise ValueError('Amounts support at most four decimal places')
        return result
    except InvalidOperation: raise ValueError('Invalid monetary amount')

def vector(text):
    from .embeddings import semantic_vector
    semantic=semantic_vector(text)
    if semantic is not None:return semantic
    counts={}
    for token in re.findall(r'\w+',text.lower()):
        key=str(int(hashlib.sha256(token.encode()).hexdigest()[:8],16)%512)
        counts[key]=counts.get(key,0)+1
    norm=sum(v*v for v in counts.values())**.5 or 1
    return {k:v/norm for k,v in counts.items()}

def normalize(row,column_mapping=None):
    result={}
    for key,value in row.items():
        if key is None: raise ValueError('Row has more fields than its header')
        key=(column_mapping or {}).get(str(key),key)
        key=re.sub(r'[^a-z0-9]+','_',str(key).strip().lower()).strip('_')
        key=ALIASES.get(key,key)
        if value is None or str(value).strip()=='': continue
        result[key]=str(money(value)) if key in MONEY else str(value).strip()
    return result

def ocr(image):
    import pytesseract
    if current_app.config.get('TESSERACT_CMD'): pytesseract.pytesseract.tesseract_cmd=current_app.config['TESSERACT_CMD']
    return pytesseract.image_to_string(image,timeout=30)

def extract(path,column_mapping=None):
    ext=path.suffix.lower(); units=[]; rows=[]; method='native'
    if ext=='.txt': units=[(None,'Text',path.read_text(encoding='utf-8-sig'))]
    elif ext=='.csv':
        text=path.read_text(encoding='utf-8-sig'); reader=csv.DictReader(io.StringIO(text))
        if not reader.fieldnames or len(set(reader.fieldnames))!=len(reader.fieldnames): raise ValueError('CSV headers must be unique')
        units=[(None,'CSV',text)]
        for i,row in enumerate(reader,2):
            if i>20002: raise ValueError('Maximum 20,000 rows per file')
            rows.append((f'CSV row {i}',normalize(row,column_mapping)))
    elif ext=='.xlsx':
        from openpyxl import load_workbook
        with zipfile.ZipFile(path) as z:
            if sum(x.file_size for x in z.infolist())>50*1024*1024: raise ValueError('Workbook expanded size exceeds limit')
        wb=load_workbook(path,read_only=True,data_only=True)
        try:
            count=0
            for ws in wb:
                iterator=ws.iter_rows(values_only=True); header=next(iterator,None)
                if not header: continue
                headers=[str(x).strip() if x is not None else f'column_{i}' for i,x in enumerate(header)]
                if len(headers)!=len(set(headers)): raise ValueError('Worksheet headers must be unique')
                lines=[','.join(headers)]
                for i,row in enumerate(iterator,2):
                    count+=1
                    if count>20000: raise ValueError('Maximum 20,000 rows per workbook')
                    if not any(v is not None for v in row): continue
                    values=normalize(dict(zip(headers,row)),column_mapping)
                    rows.append((f'{ws.title} row {i}',values)); lines.append(json.dumps(values,ensure_ascii=False))
                units.append((None,f'Worksheet {ws.title}','\n'.join(lines)))
        finally: wb.close()
    elif ext=='.docx':
        from docx import Document as Word
        with zipfile.ZipFile(path) as z:
            if sum(x.file_size for x in z.infolist())>50*1024*1024: raise ValueError('Document expanded size exceeds limit')
        doc=Word(path); text='\n'.join(p.text for p in doc.paragraphs)
        for table in doc.tables: text+='\n'+'\n'.join(' | '.join(c.text for c in row.cells) for row in table.rows)
        units=[(None,'Word document',text)]
    elif ext=='.pdf':
        import pymupdf
        from PIL import Image
        with pymupdf.open(path) as pdf:
            if len(pdf)>100: raise ValueError('Maximum 100 PDF pages')
            for i,page in enumerate(pdf,1):
                text=page.get_text()
                if len(text.strip())<15:
                    pix=page.get_pixmap(matrix=pymupdf.Matrix(1.5,1.5)); text=ocr(Image.open(io.BytesIO(pix.tobytes('png')))); method='OCR'
                units.append((i,f'Page {i}',text))
    else:
        from PIL import Image
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image: units=[(1,'Image OCR',ocr(image))]
        method='OCR'
    if not any(text.strip() for _,_,text in units): raise ValueError('No readable text found')
    if sum(len(t) for _,_,t in units)>5_000_000: raise ValueError('Extracted text exceeds limit')
    return units,rows,method

def classify(name,text):
    sample=(name+' '+text[:2000]).lower()
    for key,category in [('bank','Bank statements'),('trial','Trial balance'),('ledger','General ledger'),('payroll','Payroll documents'),('receipt','Payment receipts'),('sales','Sales invoices'),('invoice','Purchase invoices'),('expense','Expense reports'),('contract','Contracts'),('tax','Tax records'),('journal','Journal entries')]:
        if key in sample: return category
    return 'Other supporting documents'

def process(document):
    try:
        path=Path(document.file_path)
        if not path.exists():
            blob=DocumentBlob.query.filter_by(document_id=document.id).first()
            if not blob:raise ValueError('Original evidence is unavailable in storage')
            if hashlib.sha256(blob.content).hexdigest()!=document.file_hash:raise ValueError('Stored original failed its SHA-256 integrity check')
            # A durable record may have been initialized on another OS or machine.
            path=Path(current_app.config['UPLOAD_DIR'])/(str(document.id)+'-'+document.file_hash+Path(document.document_name).suffix.lower())
            path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(blob.content)
            document.file_path=str(path)
        units,rows,method=extract(Path(document.file_path),(document.metadata_json or {}).get('column_mapping'))
        Chunk.query.filter_by(document_id=document.id).delete(); Record.query.filter_by(document_id=document.id).delete()
        if document.document_type=='Auto': document.document_type=classify(document.document_name,' '.join(t for _,_,t in units))
        for page,section,text in units:
            for start in range(0,len(text),900):
                passage=text[start:start+1100]
                db.session.add(Chunk(document_id=document.id,chunk_text=passage,page_number=page,section_reference=f'{section}; chars {start}-{start+len(passage)}',embedding_reference=vector(passage)))
        for source,values in rows: db.session.add(Record(document_id=document.id,source_reference=source,values=values))
        # Unstructured field extraction retains the original text and its precise unit.
        extracted=[]
        for page,section,text in units:
            for match in re.finditer(r'(?im)^\s*(invoice[_ ]?(?:number|no)|vendor|date|currency|amount|total|net|tax)\s*[:=]\s*([^\r\n]+)',text):
                extracted.append({'field':match.group(1),'original_value':match.group(2),'page':page,'section':section,'offset':match.start(),'confidence':None,'origin':'extracted'})
        document.metadata_json={**(document.metadata_json or {}),'fields':extracted,'row_count':len(rows),'malware_scan':(document.metadata_json or {}).get('malware_scan','Not configured'),'confidence_note':'Native parsing is not a measure of document authenticity; OCR confidence is not calibrated.'}
        from .embeddings import model_version
        document.metadata_json={**document.metadata_json,'embedding_model':model_version()}
        document.extraction_confidence=None; document.extraction_method=method; document.processing_status='Processed'; document.processing_errors=None
    except Exception as exc:
        Chunk.query.filter_by(document_id=document.id).delete(); Record.query.filter_by(document_id=document.id).delete()
        document.processing_status='Failed'; document.processing_errors=str(exc)[:1000]
    db.session.flush()
    return document

def ingest(data,name,audit_id,user_id,category='Auto',description='',previous=None,column_mapping=None):
    name=secure_filename(name)
    if not name or Path(name).suffix.lower() not in EXTENSIONS: raise ValueError('Unsupported file type')
    if not data or len(data)>current_app.config['MAX_FILE_BYTES']: raise ValueError('File is empty or exceeds size limit')
    if category not in CATEGORIES+['Auto']: raise ValueError('Unknown document category')
    latest=Document.query.filter_by(audit_id=audit_id,document_name=name).order_by(Document.file_version.desc()).first()
    if previous and (not latest or latest.id!=previous): raise ValueError('Replacement must reference the latest version with the same filename')
    path=Path(current_app.config['UPLOAD_DIR'])/(uuid.uuid4().hex+Path(name).suffix.lower()); path.write_bytes(data)
    scan='Not configured'
    scanner=current_app.config.get('MALWARE_SCANNER')
    if scanner:
        try:
            result=subprocess.run([scanner,str(path)],timeout=30,capture_output=True)
            if result.returncode!=0: raise ValueError('Malware scanner rejected the file or failed')
            scan='Scanner passed'
        except Exception:
            path.unlink(missing_ok=True); raise
    document=Document(audit_id=audit_id,document_name=name,document_type=category,file_path=str(path),file_hash=hashlib.sha256(data).hexdigest(),file_version=latest.file_version+1 if latest else 1,previous_version_id=latest.id if latest else None,uploaded_by=user_id,description=description,metadata_json={'malware_scan':scan,'column_mapping':column_mapping or {}})
    db.session.add(document); db.session.flush()
    if current_app.config.get('STORE_ORIGINALS_IN_DB'):db.session.add(DocumentBlob(document_id=document.id,content=data));db.session.flush()
    process(document)
    if latest: latest.archived=True
    return document

def unpack(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        files=[x for x in archive.infolist() if not x.is_dir()]
        if len(files)>30 or sum(x.file_size for x in files)>50*1024*1024: raise ValueError('ZIP limit: 30 files, 50 MB expanded')
        for entry in files:
            name=entry.filename.replace('\\','/'); parts=PurePosixPath(name)
            if parts.is_absolute() or '..' in parts.parts or ':' in name or (entry.external_attr>>16)&0o170000==0o120000: raise ValueError('Unsafe archive entry')
            if entry.flag_bits&1: raise ValueError('Encrypted ZIP entries are unsupported')
            if Path(name).suffix.lower() not in EXTENSIONS: raise ValueError('ZIP contains unsupported file type')
        return [(PurePosixPath(x.filename.replace('\\','/')).name,archive.read(x)) for x in files]
