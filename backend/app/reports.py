import io, json
from html import escape
from .models import *

LIMITATIONS='Decision support only. Rule passes establish the stated calculation or consistency check, not authenticity. Unusual transactions are not proof of fraud. Unresolved issues require human judgment. Local retrieval uses source excerpts without LLM synthesis.'
def snapshot(audit_id):
    audit=db.session.get(Audit,audit_id)
    reqs=Requirement.query.filter_by(audit_id=audit_id).all()
    latest=AgentLog.query.filter_by(audit_id=audit_id,agent_name='Financial Anomaly Detection Agent').order_by(AgentLog.id.desc()).first()
    return {'audit':audit.json(),'organization':db.session.get(Organization,audit.organization_id).json(),'documents':[d.json() for d in Document.query.filter_by(audit_id=audit_id)],'requirements':[r.json() for r in reqs],'mappings':[m.json() for m in Mapping.query.filter(Mapping.requirement_id.in_([r.id for r in reqs]))] if reqs else [],'verification':[r.json() for r in Verification.query.filter_by(audit_id=audit_id)],'reconciliation':[r.json() for r in Reconciliation.query.filter_by(audit_id=audit_id)],'missing':[r.json() for r in EvidenceRequest.query.filter_by(audit_id=audit_id,request_status='Open')],'findings':[r.json() for r in Finding.query.filter_by(audit_id=audit_id)],'comments':[r.json() for r in Comment.query.filter_by(audit_id=audit_id)],'anomalies':(latest.output_summary or {}).get('data',{}) if latest else {},'limitations':LIMITATIONS,'generated_at':now()}

def pdf_bytes(report):
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.enums import TA_LEFT
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, KeepTogether
    output=io.BytesIO(); styles=getSampleStyleSheet()
    styles['Normal'].fontSize=9; styles['Normal'].leading=14
    story=[Paragraph('AUDITFLOW AI',styles['Title']),Paragraph('Financial audit evidence report',styles['Heading1'])]
    snap=report.snapshot
    def para(value,style='Normal'):
        text=escape(str(value)).replace('\n','<br/>')
        story.append(Paragraph(text,styles[style])); story.append(Spacer(1,6))
    para('APPROVED' if report.approved_by else 'DRAFT - HUMAN REVIEW REQUIRED','Heading2')
    para(f"Project: {snap['audit']['project_name']} | Organization: {snap['organization']['organization_name']}")
    para(f"Period: {snap['audit']['audit_period_start']} to {snap['audit']['audit_period_end']} | Generated: {snap['generated_at']}")
    for title,key in [('Audit scope','audit'),('Documents collected and source references','documents'),('Evidence requirement mapping','requirements'),('Supporting source mappings','mappings'),('Verification summary','verification'),('Reconciliation results','reconciliation'),('Missing evidence','missing'),('Anomaly indicators','anomalies'),('Discrepancies and audit observations','findings'),('Auditor and reviewer comments','comments'),('Limitations and unresolved items','limitations')]:
        para(title,'Heading2'); value=snap[key]
        if isinstance(value,list):
            if not value: para('No records at snapshot time.')
            for item in value:
                fields=[]
                for field,val in item.items():
                    if val is not None and field not in ('file_hash','metadata_json','settings','created_at','audit_id'):
                        fields.append(field.replace('_',' ').title()+': '+(json.dumps(val,ensure_ascii=True) if isinstance(val,(list,dict)) else str(val)))
                para(' | '.join(fields))
                story.append(Spacer(1,10))
        else: para(json.dumps(value,ensure_ascii=True) if isinstance(value,dict) else value)
    para('Final review status','Heading2'); para(f"Project status: {snap['audit']['status']}. Approved by user: {report.approved_by or 'Pending'}.")
    def footer(canvas,doc):
        canvas.setFont('Helvetica',8); canvas.setFillColor(colors.HexColor('#64748b')); canvas.drawString(42,24,f'AuditFlow AI | Report {report.id} | Evidence snapshot'); canvas.drawRightString(550,24,f'Page {doc.page}')
    SimpleDocTemplate(output,pagesize=(595.28,841.89),rightMargin=42,leftMargin=42,topMargin=40,bottomMargin=42).build(story,onFirstPage=footer,onLaterPages=footer)
    return output.getvalue()

def xlsx_bytes(report):
    # Backend report generation intentionally uses openpyxl as requested by the application stack.
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from decimal import Decimal, InvalidOperation
    wb=Workbook(); wb.remove(wb.active)
    for title,key in [('Evidence inventory','documents'),('Verification results','verification'),('Reconciliation results','reconciliation'),('Missing evidence','missing'),('Audit findings','findings'),('Document references','mappings'),('Review comments','comments')]:
        ws=wb.create_sheet(title); rows=report.snapshot[key]
        headers=list(dict.fromkeys(k for row in rows for k in row)) if rows else ['Result']
        ws.append(headers)
        for cell in ws[1]: cell.font=Font(bold=True,color='FFFFFF'); cell.fill=PatternFill('solid',fgColor='14283F'); cell.alignment=Alignment(wrap_text=True)
        for row in rows:
            values=[]
            for key in headers:
                value=row.get(key)
                if isinstance(value,(dict,list)): value=json.dumps(value,ensure_ascii=True)
                if key in ('expected_value','actual_value','difference','expected_amount','actual_amount','financial_impact') and isinstance(value,str):
                    try:
                        number=Decimal(value)
                        # Excel has 15 significant-digit precision; preserve larger values as text.
                        if len(number.as_tuple().digits)<=15:value=number
                    except InvalidOperation:pass
                # Uploaded content is never interpreted as an Excel formula.
                if isinstance(value,str) and value.startswith(('=','+','-','@')): value="'"+value
                values.append(value)
            ws.append(values)
        if not rows: ws.append(['No records at snapshot time'])
        ws.freeze_panes='A2'; ws.auto_filter.ref=ws.dimensions
        for column in ws.columns:
            ws.column_dimensions[column[0].column_letter].width=min(65,max(18,max(len(str(c.value or '')) for c in column[:100])+2))
            for cell in column[1:]:
                cell.alignment=Alignment(vertical='top',wrap_text=True)
                if isinstance(cell.value,Decimal):cell.number_format='#,##0.00;[Red](#,##0.00);"-"'
    out=io.BytesIO(); wb.save(out); return out.getvalue()
