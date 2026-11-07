import re
from .models import db, Document, Chunk, RetrievalHistory
from .processing import vector
from .vector_index import similarities
from .embeddings import model_version,model_name

def retrieve(audit_id,query,top_k=5,category=None,document_id=None):
    documents=Document.query.filter_by(audit_id=audit_id,archived=False,processing_status='Processed')
    if category: documents=documents.filter_by(document_type=category)
    if document_id: documents=documents.filter_by(id=document_id)
    docs={d.id:d for d in documents.all()}
    if not docs: return []
    if any((d.metadata_json or {}).get('embedding_model','token-hash-v1')!=model_version() for d in docs.values()):raise ValueError('Embedding model changed. Reindex active audit documents before searching.')
    query_vector=vector(query); tokens=set(re.findall(r'\w+',query.lower())); results=[]
    chunks=Chunk.query.filter(Chunk.document_id.in_(docs)).all()
    scores=similarities(chunks,query_vector)
    for chunk in chunks:
        embedding=chunk.embedding_reference or vector(chunk.chunk_text)
        cosine=scores.get(chunk.id,0)
        lexical=len(tokens & set(re.findall(r'\w+',chunk.chunk_text.lower())))/max(len(tokens),1)
        # Require actual lexical overlap: hash collisions must not manufacture evidence.
        if lexical<=0 and (not model_name() or cosine<0.3): continue
        score=round(.55*cosine+.45*lexical,4); doc=docs[chunk.document_id]
        results.append({'chunk_id':chunk.id,'document_id':doc.id,'document_name':doc.document_name,'version':doc.file_version,'page_number':chunk.page_number,'section_reference':chunk.section_reference,'score':score,'text':chunk.chunk_text})
    return sorted(results,key=lambda x:x['score'],reverse=True)[:top_k]

def answer(audit_id,user_id,query,top_k=5,category=None,document_id=None):
    if not category and not document_id:
        from .assistant_tools import tool_query
        tool_result=tool_query(audit_id,query)
        if tool_result is not None:
            db.session.add(RetrievalHistory(audit_id=audit_id,user_id=user_id,query=query,response=tool_result))
            return tool_result
    hits=retrieve(audit_id,query,top_k,category,document_id)
    model=None; warning=None
    try:
        from .llm import select_quotes
        selected=select_quotes(query,hits)
        if selected: hits=selected['sources']; model=selected['model']
    except Exception:
        warning='Optional model selection unavailable or invalid; local source retrieval was used.'
    response={'answer':'The following source passages match your question. Review their context before drawing a conclusion.' if hits else 'Insufficient evidence: no relevant passage could be located in the active documents for this audit. Upload additional supporting evidence.','sources':hits,'mode':'Local extractive retrieval','limitations':'Local hashing and keyword retrieval; no LLM interpretation or audit opinion.'}
    response.update(model=model,warning=warning)
    if model: response['mode']='LLM-selected validated source quotes'; response['limitations']='Model-selected excerpts were checked against original retrieved text. They do not establish an audit conclusion.'
    db.session.add(RetrievalHistory(audit_id=audit_id,user_id=user_id,query=query,response=response))
    return response
