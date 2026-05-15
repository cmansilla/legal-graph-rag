import re
from core.config import logger

try:
    from sentence_transformers import SentenceTransformer
    logger.info("🤖 Cargando modelo Sentences-Transformers (Singleton)...")
    embedding_model = SentenceTransformer('sentence-transformers/distiluse-base-multilingual-cased-v2', device='cpu')
    emb_dim = embedding_model.get_sentence_embedding_dimension()
except Exception as e:
    logger.error(f"Error cargando el modelo de embeddings: {e}")
    embedding_model = None
