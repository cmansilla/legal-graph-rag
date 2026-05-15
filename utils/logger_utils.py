import os
import re
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
