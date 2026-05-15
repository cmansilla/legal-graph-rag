import os
from dotenv import load_dotenv
import logging

# Cargar variables de entorno
load_dotenv()

# Configurar Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("LexRAG")

# --- CONFIGURACIONES GLOBALES ---
FAISS_INDEX_PATH = "data/indices/faiss_index_pro.bin"
FAISS_META_PATH = "data/indices/faiss_meta_pro.pkl"
GRAPH_PATH = "data/indices/graph_juris_pro.pkl"
BM25_PATH = "data/indices/bm25_index_pro.pkl"

MAX_TOKENS_CONTEXT = 30000 
CHUNK_SIZE = 512
CHUNK_OVERLAP = 50

# --- APIS SECRETAS ---
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
SERPER_API_KEY = os.environ.get("SERPER_API_KEY")

if not DEEPSEEK_API_KEY:
    logger.warning("No se encontró DEEPSEEK_API_KEY en .env")

