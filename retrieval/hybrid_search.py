import re
import faiss
import pickle
import numpy as np
from rank_bm25 import BM25Okapi
from core.config import FAISS_INDEX_PATH, FAISS_META_PATH, BM25_PATH
from core.embedding import embedding_model

def get_hybrid_context(hyde_query, top_k=7):
    # FAISS
    index = faiss.read_index(FAISS_INDEX_PATH)
    with open(FAISS_META_PATH, 'rb') as f:
        meta_data = pickle.load(f)
        
    query_vector = embedding_model.encode(hyde_query)
    distances, indices = index.search(np.array([query_vector]).astype('float32'), top_k * 3)
    faiss_chunk_indices = [i for i in indices[0] if i != -1]
    
    # BM25
    with open(BM25_PATH, 'rb') as f:
        bm25_data = pickle.load(f)
    bm25 = bm25_data['bm25']
    
    clean_query = re.sub(r'[^\w\s]', '', hyde_query)
    tokenized_query = clean_query.lower().split()
    doc_scores = bm25.get_scores(tokenized_query)
    bm25_chunk_indices = np.argsort(doc_scores)[::-1][:top_k * 3]
    
    # RRF FUSION en Chunks para extraer el contenido exacto
    chunk_scores = {}
    k_rrf = 60
    for rank, idx in enumerate(faiss_chunk_indices):
        chunk_scores[idx] = chunk_scores.get(idx, 0) + 1.0 / (k_rrf + rank + 1)
    for rank, idx in enumerate(bm25_chunk_indices):
        chunk_scores[idx] = chunk_scores.get(idx, 0) + 1.0 / (k_rrf + rank + 1)
        
    sorted_chunks = sorted(chunk_scores.items(), key=lambda x: x[1], reverse=True)
    top_chunks_indices = [c[0] for c in sorted_chunks[:top_k * 2]]
    
    # Obtenemos los 7 documentos principales basándonos en los chunks más relevantes
    all_unique_docs = list(dict.fromkeys([meta_data[i]["doc_id"] for i in top_chunks_indices]))
    final_top_docs = all_unique_docs[:top_k]
    
    # Extraer texto SOLO de los chunks que pertenecen a los procedentes Top 7
    texts = []
    for i in top_chunks_indices:
        m = meta_data[i]
        if m['doc_id'] in final_top_docs:
            texts.append(f"[Doc: {m['doc_id']}]\n{m['text']}")
        
    return final_top_docs, "\n\n".join(texts)
