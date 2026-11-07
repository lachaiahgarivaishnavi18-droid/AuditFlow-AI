"""FAISS index constructed only from an authorized audit's active chunks."""
import numpy as np
import faiss
def similarities(chunks,query_vector):
    if not chunks: return {}
    dimensions=1+max([int(k) for c in chunks for k in (c.embedding_reference or {})]+[int(k) for k in query_vector]+[0])
    matrix=np.zeros((len(chunks),dimensions),dtype='float32'); query=np.zeros((1,dimensions),dtype='float32')
    for i,chunk in enumerate(chunks):
        for key,value in (chunk.embedding_reference or {}).items(): matrix[i,int(key)]=value
    for key,value in query_vector.items(): query[0,int(key)]=value
    index=faiss.IndexFlatIP(dimensions); index.add(matrix); scores,indices=index.search(query,len(chunks))
    return {chunks[int(i)].id:float(score) for i,score in zip(indices[0],scores[0]) if i>=0}
