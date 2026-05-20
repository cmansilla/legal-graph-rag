import os
import re
import json
from datetime import datetime
from core.config import logger

def save_query_log(query, response, context):
    log_dir = "consultas_guardadas"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    clean_query = re.sub(r'[^a-zA-Z0-9]', '_', query)[:30].strip('_')
    base_filename = os.path.join(log_dir, f"{timestamp}_{clean_query}")
    
    try:
        # Save md
        with open(base_filename + ".md", "w", encoding="utf-8") as f:
            f.write(f"# Consulta Jurídica: {timestamp}\n\n")
            f.write(f"## Pregunta\n> {query}\n\n")
            f.write(f"## Dictamen (IA)\n\n{response}\n\n")
            f.write("## Contexto Base\n```text\n")
            f.write(context[:2500] + "\n...(truncado)...\n```\n")
            
        # Save txt
        with open(base_filename + ".txt", "w", encoding="utf-8") as f:
            f.write(f"QUERY: {query}\n\nRESPONSE:\n{response}\n\nCONTEXT:\n{context}")
            
        logger.info(f"💾 Consulta guardada en {log_dir}/{timestamp}_{clean_query}.md")
    except Exception as e:
        logger.warning(f"No se pudo guardar la consulta: {e}")


def save_chunk_audit(query, hybrid_audit, graph_audit, response, decision, hyde_query, elapsed=None):
    """
    Guarda un JSON estructurado con la auditoría granular de chunks.
    """
    log_dir = "consultas_guardadas"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    clean_query = re.sub(r'[^a-zA-Z0-9]', '_', query)[:30].strip('_')
    base_filename = os.path.join(log_dir, f"{timestamp}_{clean_query}")
    
    audit = {
        "metadata": {
            "timestamp": timestamp,
            "query": query,
            "query_clean": clean_query,
            "decision": decision,
            "hyde_query": hyde_query,
            "elapsed_seconds": elapsed
        },
        "retrieval": {
            "hybrid": hybrid_audit,
            "graph": graph_audit
        },
        "response": {
            "text": response,
            "tokens_estimados": len(response) // 4 if response else 0
        }
    }
    
    try:
        audit_path = base_filename + "_audit.json"
        with open(audit_path, "w", encoding="utf-8") as f:
            json.dump(audit, f, ensure_ascii=False, indent=2)
        logger.info(f"🔍 Auditoría granular guardada en {audit_path}")
    except Exception as e:
        logger.warning(f"No se pudo guardar la auditoría granular: {e}")
