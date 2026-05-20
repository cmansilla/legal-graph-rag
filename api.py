from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
import time
import asyncio
import json
from agents.router import route_query_and_hyde
from agents.synthesizer import generate_rag_synthesis
from retrieval.web_search import serper_search
from retrieval.hybrid_search import get_hybrid_context
from agents.graph_analyst import GraphAnalyst
from utils.logger_utils import save_query_log
from core.llm_clients import groq_client
from core.config import logger

app = FastAPI(title="Lex RAG B2B API")

# Permitir CORS para el frontend Next.js (Localhost:3000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def generate_rag_stream(query: str, history=None):
    if history is None:
        history = []
        
    logger.info("🧠 API Orchestrator Evaluando Query...")
    
    t0 = time.time()
    decision, hyde = route_query_and_hyde(query, history)
    
    if "WEB" in decision:
        yield {"data": json.dumps({"type": "info", "content": "🌐 Búsqueda web activada..."})}
        web_context = serper_search(query)
        contexto_raw = f"=== CONTEXTO WEB ===\n{web_context}"
    else:
        yield {"data": json.dumps({"type": "info", "content": "📚 Buscando en 96,143 expedientes (FAISS + BM25)..."})}
        await asyncio.sleep(0.1) # Pequeña pausa para que UI registre
        top_docs, text_context, hybrid_audit = get_hybrid_context(hyde, top_k=7)
        
        yield {"data": json.dumps({"type": "info", "content": "🕸️ Trazando grafo de jueces y precedentes..."})}
        await asyncio.sleep(0.1)
        _ga = GraphAnalyst()
        graph_context, graph_audit = _ga.analyze(top_docs)
        
        contexto_raw = f"{text_context}\n\n{graph_context}"

    # Mando la data recolectada al agente generador
    elapsed = time.time() - t0
    async for chunk in generate_rag_synthesis(
        query=query,
        decision=decision,
        hyde_query=hyde,
        web_context=web_context if "WEB" in decision else "",
        hybrid_context=text_context if "WEB" not in decision else "",
        graph_context=graph_context if "WEB" not in decision else "",
        history=history,
        hybrid_audit=hybrid_audit if "WEB" not in decision else None,
        graph_audit=graph_audit if "WEB" not in decision else None,
        elapsed=elapsed
    ):
        yield chunk

@app.post("/api/query")
async def api_query(request: Request):
    data = await request.json()
    query = data.get("query", "")
    history = data.get("history", [])
    if not query:
        return {"error": "Query is empty"}
    
    return EventSourceResponse(generate_rag_stream(query, history))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
