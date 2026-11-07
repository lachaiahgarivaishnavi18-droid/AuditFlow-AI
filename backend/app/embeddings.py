"""Optional local semantic embeddings; explicit configuration, no silent fallback."""
import os
from functools import lru_cache
def model_name():return os.getenv('EMBEDDING_MODEL','').strip()
def model_version():return model_name() or 'token-hash-v1'
@lru_cache(maxsize=1)
def encoder(name):
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(name,local_files_only=os.getenv('ALLOW_MODEL_DOWNLOAD','false').lower()!='true',trust_remote_code=False)
def semantic_vector(text):
    name=model_name()
    if not name:return None
    values=encoder(name).encode(text,normalize_embeddings=True)
    return {str(i):float(value) for i,value in enumerate(values)}
