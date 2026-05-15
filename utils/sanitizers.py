import re
from core.config import CHUNK_SIZE, CHUNK_OVERLAP

def normalize_entity(text):
    if not text or not isinstance(text, str): return ""
    t = text.lower().strip()
    t = re.sub(r'\b(dr|dra|señor|señora|magistrado|magistrada|juez|jueza|vocal)\b\.?', '', t)
    t = re.sub(r'[^a-záéíóúñ0-9\s-]', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t

def chunk_text(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    words = text.split()
    chunks = []
    for i in range(0, len(words), max(1, chunk_size - overlap)):
        chunk = " ".join(words[i:i + chunk_size])
        chunks.append(chunk)
    return chunks
