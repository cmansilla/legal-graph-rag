"""
api_busqueda_juridica.py - API HTTP para busqueda juridica

Sirve la funcionalidad de kindly-web-search como API REST,
para que la app instalada en otros equipos pueda consumirla
sin depender de Python ni de Hermes Agent.

USO:
    python api_busqueda_juridica.py
    # Servidor en http://localhost:8766
    
    curl http://localhost:8766/buscar \
        -H "Content-Type: application/json" \
        -d '{"consulta": "desnaturalizacion CAS Peru", "num": 3}'
    
    curl http://localhost:8766/extraer \
        -H "Content-Type: application/json" \
        -d '{"url": "https://ejemplo.com/norma"}'

DEPENDENCIAS:
    pip install fastapi uvicorn httpx
    
    O simplemente: desde el venv de kindly-web-search
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl

# Importar nuestro módulo de búsqueda
from busqueda_juridica import BusquedaJuridica

app = FastAPI(
    title="API Búsqueda Jurídica",
    description="Búsqueda web + extracción de contenido para KGraphResolucionesV3",
    version="1.0.0",
)

# Instancia global del buscador (comparte la SERPER_API_KEY del entorno)
buscador = BusquedaJuridica()


# --- Modelos de request/response ---

class BuscarRequest(BaseModel):
    consulta: str
    num: int = 5


class ResultadoItem(BaseModel):
    title: str
    link: str
    snippet: str
    page_content: str | None = None
    contenido_completo: str | None = None


class BuscarResponse(BaseModel):
    resultados: list[ResultadoItem]
    total: int
    advertencia: str | None = None


class ExtraerRequest(BaseModel):
    url: str


class ExtraerResponse(BaseModel):
    url: str
    contenido: str
    caracteres: int


# --- Endpoints ---

@app.get("/health")
async def health():
    """Health check simple."""
    return {"status": "ok", "serper_key_set": bool(os.environ.get("SERPER_API_KEY"))}


@app.post("/buscar", response_model=BuscarResponse)
async def buscar(req: BuscarRequest):
    """
    Buscar en la web y devolver resultados con snippet.
    
    - consulta: término de búsqueda
    - num: cantidad de resultados (default: 5, max: 20)
    """
    num = min(max(1, req.num), 20)
    
    resultados = await buscador.buscar(req.consulta, num_resultados=num)
    
    items = [ResultadoItem(**r) for r in resultados]
    
    advertencia = None
    if buscador._advertencia_creditos:
        advertencia = "Sin créditos en Serper. Recarga o configura TAVILY_API_KEY."
    elif buscador._ultimo_error:
        advertencia = f"Error en búsqueda: {buscador._ultimo_error[:200]}"
    
    return BuscarResponse(resultados=items, total=len(items), advertencia=advertencia)


@app.post("/buscar-completo", response_model=BuscarResponse)
async def buscar_completo(req: BuscarRequest):
    """
    Buscar y extraer el contenido completo de cada resultado.
    Más lento pero devuelve la página completa.
    """
    num = min(max(1, req.num), 5)  # Limitado a 5 por tiempo
    
    resultados = await buscador.buscar_y_extraer(req.consulta, num_resultados=num)
    
    items = [ResultadoItem(**r) for r in resultados]
    
    return BuscarResponse(resultados=items, total=len(items))


@app.post("/extraer", response_model=ExtraerResponse)
async def extraer(req: ExtraerRequest):
    """
    Extraer el contenido completo de una URL en Markdown.
    """
    try:
        contenido = await buscador.extraer_url(req.url)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error al extraer: {e}")
    
    return ExtraerResponse(
        url=req.url,
        contenido=contenido,
        caracteres=len(contenido),
    )


@app.post("/verificar-cita")
async def verificar_cita(texto: str, fuente_esperada: str = ""):
    """
    Verificar una cita legal contra la web.
    
    - texto: texto de la cita a verificar
    - fuente_esperada: (opcional) fuente que se espera encontrar
    
    Returns: confirmación o corrección
    """
    consulta = f'"{texto}"' if len(texto) < 100 else texto[:100]
    if fuente_esperada:
        consulta += f" {fuente_esperada}"
    
    resultados = await buscador.buscar(consulta, num_resultados=3)
    
    if not resultados:
        return {
            "verificada": False,
            "mensaje": "No se encontraron fuentes para verificar esta cita.",
            "fuentes_encontradas": [],
        }
    
    fuentes = [
        {
            "titulo": r["title"],
            "url": r["link"],
            "snippet": r["snippet"][:300],
        }
        for r in resultados
    ]
    
    return {
        "verificada": True,
        "mensaje": f"Se encontraron {len(fuentes)} fuente(s) relacionadas.",
        "fuentes_encontradas": fuentes,
    }


# --- Entry point ---

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("API_PORT", "8766"))
    print(f"Iniciando API de Búsqueda Jurídica en http://localhost:{port}")
    print(f"Documentación: http://localhost:{port}/docs")
    uvicorn.run(app, host="0.0.0.0", port=port)
