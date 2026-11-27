"""Web search via Serper API."""
import os
import requests
from core.config import logger

SERPER_URL = "https://google.serper.dev/search"

def serper_search(query: str, num_results: int = 3) -> str:
    """
    Busca en Google via Serper API y retorna texto plano con resultados.
    """
    api_key = os.environ.get("SERPER_API_KEY")
    if not api_key:
        logger.warning("SERPER_API_KEY no configurada — web search desactivado")
        return ""

    try:
        resp = requests.post(
            SERPER_URL,
            json={"q": query, "num": num_results},
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            timeout=15
        )
        resp.raise_for_status()
        data = resp.json()

        lines = []
        for item in data.get("organic", []):
            title = item.get("title", "")
            link = item.get("link", "")
            snippet = item.get("snippet", "")
            lines.append(f"- {title}")
            lines.append(f"  {link}")
            lines.append(f"  {snippet}")
            lines.append("")

        return "\n".join(lines) if lines else "(Sin resultados web)"
    except Exception as e:
        logger.warning(f"Serper search error: {e}")
        return ""
