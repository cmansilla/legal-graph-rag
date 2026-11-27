"""
busqueda_juridica.py - Módulo de búsqueda web para KGraphResolucionesV3

Usa la lógica de kindly-web-search-mcp-server como librería nativa,
sin depender de Hermes Agent ni del protocolo MCP.

Uso:
    from busqueda_juridica import BusquedaJuridica
    
    bj = BusquedaJuridica(serper_api_key="tu_key")
    
    # Búsqueda simple
    resultados = await bj.buscar("desnaturalización contrato CAS Perú")
    
    # Búsqueda + extraer contenido completo del primer resultado
    contenido = await bj.buscar_y_extraer("Ley Servir actualizada 2025")
    
    # Extraer URL específica
    texto = await bj.extraer_url("https://ejemplo.com/norma-legal")
    
    # Buscar solo sitios peruanos
    resultados = await bj.buscar("site:gob.pe indemnización daños")
"""

from __future__ import annotations

import asyncio
import os
from typing import Optional

import httpx


class BusquedaJuridica:
    """
    Wrapper de búsqueda jurídica usando kindly-web-search como librería.
    
    No requiere MCP, no requiere Hermes. Funciona en cualquier equipo
    con Python >=3.10 y las dependencias instaladas.
    """

    def __init__(
        self,
        serper_api_key: str | None = None,
        tavily_api_key: str | None = None,
        searxng_url: str | None = None,
        timeout: int = 30,
    ):
        # Intentar leer del entorno si no se pasa explícitamente
        self._serper_key = serper_api_key or os.environ.get("SERPER_API_KEY", "")
        self._tavily_key = tavily_api_key or os.environ.get("TAVILY_API_KEY", "")
        self._searxng_url = searxng_url or os.environ.get("SEARXNG_BASE_URL", "")
        self._timeout = timeout

        # Import tardío para no romper si no está instalado
        self._importado = False
        self._search_web = None
        self._resolve_content = None
        self._ultimo_error = None
        self._advertencia_creditos = False

    def _importar_modulos(self):
        """Importar los módulos de kindly-web-search bajo demanda."""
        if self._importado:
            return

        import sys
        import pathlib

        # Ruta al repo clonado (ajustar si se mueve)
        repo = pathlib.Path(__file__).resolve().parent.parent / "kindly-web-search-mcp-server" / "src"
        if repo.exists():
            sys.path.insert(0, str(repo))
        else:
            # Intentar desde instalación pip
            pass

        from kindly_web_search_mcp_server.search import search_web as _sw
        from kindly_web_search_mcp_server.content.resolver import (
            resolve_page_content_markdown as _rp,
        )

        self._search_web = _sw
        self._resolve_content = _rp
        self._importado = True

    async def buscar(
        self,
        consulta: str,
        num_resultados: int = 5,
    ) -> list[dict]:
        """
        Buscar en la web y devolver resultados con título, URL, snippet.
        
        Args:
            consulta: Término de búsqueda (ej: "desnaturalización CAS Perú")
            num_resultados: Cantidad de resultados (default: 5)
        
        Returns:
            Lista de dicts con keys: title, link, snippet, page_content
        """
        self._importar_modulos()
        
        os.environ.setdefault("SERPER_API_KEY", self._serper_key)
        
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                resultados = await self._search_web(
                    consulta,
                    num_results=num_resultados,
                    http_client=client,
                )
            except Exception as e:
                self._ultimo_error = str(e)
                if "credits" in str(e).lower():
                    self._advertencia_creditos = True
                return []
        
        return [
            {
                "title": r.title,
                "link": r.link,
                "snippet": r.snippet,
                "page_content": r.page_content,
            }
            for r in resultados
        ]

    async def extraer_url(self, url: str) -> str:
        """
        Extraer contenido completo de una URL en formato Markdown.
        
        Args:
            url: URL a extraer
        
        Returns:
            Contenido de la página en Markdown
        """
        self._importar_modulos()
        
        os.environ.setdefault("SERPER_API_KEY", self._serper_key)
        
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            contenido = await self._resolve_content(url)
        
        return contenido

    async def buscar_y_extraer(
        self,
        consulta: str,
        num_resultados: int = 3,
    ) -> list[dict]:
        """
        Buscar y extraer el contenido completo de cada resultado.
        
        Args:
            consulta: Término de búsqueda
            num_resultados: Cantidad de resultados a extraer
        
        Returns:
            Lista con título, URL y contenido completo
        """
        resultados = await self.buscar(consulta, num_resultados)
        
        for r in resultados:
            try:
                contenido = await self._resolve_content(r["link"])
                r["contenido_completo"] = contenido
            except Exception as e:
                r["contenido_completo"] = f"[Error al extraer: {e}]"
        
        return resultados

    def buscar_sync(self, consulta: str, num_resultados: int = 5) -> list[dict]:
        """Versión síncrona de buscar() para usar sin async."""
        return asyncio.run(self.buscar(consulta, num_resultados))

    def extraer_url_sync(self, url: str) -> str:
        """Versión síncrona de extraer_url()."""
        return asyncio.run(self.extraer_url(url))


# ── Ejemplo de uso directo ─────────────────────────────────────

if __name__ == "__main__":

    async def demo():
        bj = BusquedaJuridica()
        
        print("=== Búsqueda jurídica de prueba ===\n")
        
        resultados = await bj.buscar(
            "desnaturalización contrato administrativo servicios CAS Perú",
            num_resultados=3,
        )
        
        for i, r in enumerate(resultados, 1):
            print(f"{i}. {r['title']}")
            print(f"   URL: {r['link']}")
            print(f"   Snippet: {r['snippet'][:200]}...\n")
        
        if resultados:
            print("--- Extrayendo contenido del primer resultado ---")
            contenido = await bj.extraer_url(resultados[0]["link"])
            print(f"Contenido ({len(contenido)} chars):")
            print(contenido[:500])

    asyncio.run(demo())
