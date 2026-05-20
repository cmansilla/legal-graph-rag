import re
import os
import json
import faiss
import pickle
import numpy as np
from rank_bm25 import BM25Okapi
from core.config import FAISS_INDEX_PATH, FAISS_META_PATH, BM25_PATH, METADATA_DOCS_PATH
from core.embedding import embedding_model

# Cache de metadatos legibles (RTF N°, CAS. N°, EXP. N°)
_docs_metadata = {}
def _load_docs_metadata():
    global _docs_metadata
    if not _docs_metadata and METADATA_DOCS_PATH and os.path.exists(METADATA_DOCS_PATH):
        try:
            with open(METADATA_DOCS_PATH, 'r', encoding='utf-8') as f:
                _docs_metadata = json.load(f)
        except Exception:
            _docs_metadata = {}

def _doc_label(doc_id):
    """Retorna el identificador legible (CAS. N° XXXX, RTF N° XXXX, etc.)"""
    _load_docs_metadata()
    meta = _docs_metadata.get(doc_id, {})
    if isinstance(meta, dict):
        return meta.get("identificador", "") or doc_id
    return doc_id

def get_hybrid_context(hyde_query, top_k=7, strategy=None):
    """Búsqueda híbrida FAISS+BM25 con RRF fusion.

    Args:
        hyde_query: str — query expandida por HyDE
        top_k: int — documentos a retornar (default, usado si strategy es None)
        strategy: dict — estrategia del RetrievalStrategist (opcional)

    Returns:
        (top_docs, text_context, audit_dict)
    """
    # Aplicar estrategia si existe
    if strategy:
        top_k = strategy.get("top_k", top_k)
        top_k_mult = strategy.get("top_k_mult", 3)
        retrieval_mode = strategy.get("retrieval_mode", "hybrid")
        k_rrf = strategy.get("k_rrf", 60)
    else:
        top_k_mult = 3
        retrieval_mode = "hybrid"
        k_rrf = 60

    audit = {
        "query": hyde_query,
        "top_k": top_k,
        "strategy": strategy,
        "faiss_raw": [],
        "bm25_raw": [],
        "rrf_ranked": [],
        "chunks_filtered_out": [],
        "final_docs": [],
        "fusion_params": {"k_rrf": k_rrf, "top_k_mult": top_k_mult, "mode": retrieval_mode}
    }
    # FAISS
    index = faiss.read_index(FAISS_INDEX_PATH)
    with open(FAISS_META_PATH, 'rb') as f:
        meta_data = pickle.load(f)
        
    query_vector = embedding_model.encode(hyde_query)
    faiss_top_k = top_k * top_k_mult
    if retrieval_mode == "lexical_only":
        # Saltar FAISS en modo solo léxico
        faiss_chunk_indices = []
        distances_result = ([], [])
    else:
        distances, indices = index.search(np.array([query_vector]).astype('float32'), faiss_top_k)
        faiss_chunk_indices = [i for i in indices[0] if i != -1]
    
    # Audit: capturar FAISS raw scores (solo si se ejecutó)
    if retrieval_mode != "lexical_only":
        for rank, idx in enumerate(faiss_chunk_indices):
            m = meta_data[idx]
            audit["faiss_raw"].append({
                "chunk_index": int(idx),
                "doc_id": m['doc_id'],
                "distance": float(distances[0][rank]),
                "rank": rank + 1,
                "snippet": m['text'][:200]
            })
    
    # BM25
    with open(BM25_PATH, 'rb') as f:
        bm25_data = pickle.load(f)
    bm25 = bm25_data['bm25']
    bm25_mult = top_k_mult  # same multiplier
    bm25_top_k = top_k * bm25_mult
    clean_query = re.sub(r'[^\w\s]', '', hyde_query)
    tokenized_query = clean_query.lower().split()
    doc_scores = bm25.get_scores(tokenized_query)

    if retrieval_mode == "semantic_only":
        # Saltar BM25 en modo solo semántico
        bm25_chunk_indices = []
    else:
        bm25_chunk_indices = np.argsort(doc_scores)[::-1][:bm25_top_k]

    # Audit: capturar BM25 raw scores (solo si se ejecutó)
    if retrieval_mode != "semantic_only":
        for rank, idx in enumerate(bm25_chunk_indices):
            m = meta_data[idx]
            audit["bm25_raw"].append({
                "chunk_index": int(idx),
                "doc_id": m['doc_id'],
                "bm25_score": float(doc_scores[idx]),
                "rank": rank + 1,
                "snippet": m['text'][:200]
            })
    
    # RRF FUSION en Chunks para extraer el contenido exacto
    chunk_scores = {}
    k_rrf = 60
    for rank, idx in enumerate(faiss_chunk_indices):
        chunk_scores[idx] = chunk_scores.get(idx, 0) + 1.0 / (k_rrf + rank + 1)
    for rank, idx in enumerate(bm25_chunk_indices):
        chunk_scores[idx] = chunk_scores.get(idx, 0) + 1.0 / (k_rrf + rank + 1)
        
    sorted_chunks = sorted(chunk_scores.items(), key=lambda x: x[1], reverse=True)
    top_chunks_indices = [c[0] for c in sorted_chunks[:top_k * 2]]
    
    # Audit: RRF fusion ranking
    for rank, (chunk_idx, score) in enumerate(sorted_chunks):
        m = meta_data[chunk_idx]
        entry = {
            "chunk_index": int(chunk_idx),
            "doc_id": m['doc_id'],
            "rrf_score": float(score),
            "rank": rank + 1,
            "in_top_chunks": chunk_idx in top_chunks_indices,
            "snippet": m['text'][:200]
        }
        if chunk_idx in top_chunks_indices:
            audit["rrf_ranked"].append(entry)
        else:
            audit["chunks_filtered_out"].append(entry)
    
    # Obtenemos los 7 documentos principales basándonos en los chunks más relevantes
    all_unique_docs = list(dict.fromkeys([meta_data[i]["doc_id"] for i in top_chunks_indices]))
    final_top_docs = all_unique_docs[:top_k]
    
    # Audit: docs finales seleccionados
    audit["final_docs"] = [{
        "doc_id": d,
        "label": _doc_label(d),
        "rank": rank + 1
    } for rank, d in enumerate(final_top_docs)]
    
    # Extraer texto SOLO de los chunks que pertenecen a los procedentes Top 7
    texts = []
    for i in top_chunks_indices:
        m = meta_data[i]
        if m['doc_id'] in final_top_docs:
            label = _doc_label(m['doc_id'])
            texts.append(f"**{label}** → Jurisprudencia/{m['doc_id']}\n{m['text']}")
        
    return final_top_docs, "\n\n".join(texts), audit
