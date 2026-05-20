import os
from groq import Groq
from openai import OpenAI
from core.config import logger

# --- Cliente Groq (fallback principal) ---
groq_api_key = os.environ.get("GROQ_API_KEY")
if groq_api_key:
    groq_client = Groq(api_key=groq_api_key)
else:
    logger.error("No se encontró GROQ_API_KEY")
    groq_client = None

# --- Cliente DeepSeek (proveedor principal) ---
deepseek_api_key = os.environ.get("DEEPSEEK_API_KEY")
deepseek_client = None
if deepseek_api_key:
    try:
        deepseek_client = OpenAI(
            api_key=deepseek_api_key,
            base_url="https://api.deepseek.com"
        )
        logger.info("Cliente DeepSeek inicializado correctamente")
    except Exception as e:
        logger.warning(f"Error inicializando DeepSeek: {e}")
        deepseek_client = None
else:
    logger.warning("No se encontró DEEPSEEK_API_KEY en .env — solo se usará Groq")
