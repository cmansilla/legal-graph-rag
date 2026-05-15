import os
from groq import Groq
from core.config import logger

groq_api_key = os.environ.get("GROQ_API_KEY")
if groq_api_key:
    groq_client = Groq(api_key=groq_api_key)
else:
    logger.error("No se encontró GROQ_API_KEY")
    groq_client = None

# DeepSeek is typically called via Groq's openai wrapper in this project or direct 
# If a direct client is needed, it would be initialized here as well.
