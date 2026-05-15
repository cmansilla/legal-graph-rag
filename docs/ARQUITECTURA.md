# Lex RAG — Arquitectura del Sistema

## Diagrama de Flujo General

```
+------------------------------------------------------------------+
|                        LEX RAG SYSTEM                             |
|         Motor de Consultas Jurisprudenciales (GraphRAG)           |
+------------------------------------------------------------------+

                         +-------------------+
                         |   USUARIO (CLI)   |
                         |  "que dice la     |
                         |  jurisprudencia   |
                         |  sobre desalojo?" |
                         +--------+----------+
                                  |
                                  v
+--------------------------------------------------------------------+
|                    FASE 1: RECUPERACION (RETRIEVAL)                  |
+--------------------------------------------------------------------+
|                                                                     |
|  Pregunta del Usuario                                               |
|         |                                                            |
|         v                                                            |
|  +--------------+                                                    |
|  |  Embedding   |  SentenceTransformer(distiluse-base-multilingual)  |
|  |  + FAISS     |  Busqueda semantica: top 15 chunks                |
|  +------+-------+                                                    |
|         |                                                            |
|         v                                                            |
|  +--------------+                                                    |
|  |  Dedup +     |  Agrupa chunks por documento,                    |
|  |  Diversidad  |  max 3 documentos distintos                       |
|  +------+-------+                                                    |
|         |                                                            |
|         v                                                            |
|  +--------------+                                                    |
|  |  NetworkX    |  Traversal de 2 saltos:                          |
|  |  GraphRAG    |  Doc -> Juez/Ley/Actor -> Otros Docs             |
|  +------+-------+                                                    |
|         |                                                            |
|         v                                                            |
|  +--------------+                                                    |
|  |  Metadata    |  Mapping: filename -> identificador legible       |
|  |  Docs        |  (RTF N°, CAS. N°, EXP. N°) desde HTML           |
|  +------+-------+                                                    |
|         |                                                            |
|         v                                                            |
+--------------------------------------------------------------------+
|                    FASE 2: GENERACION (LLM)                          |
+--------------------------------------------------------------------+
|                                                                     |
|  +--------------+                                                    |
|  |  Prompt      |  Template con 2 escenarios:                      |
|  |  Template    |  A) Datos relevantes -> 4-partes analiticas     |
|  |              |  B) Datos irrelevantes -> Resumen conciso        |
|  +------+-------+                                                    |
|         |                                                            |
|         v                                                            |
|  +--------------+                                                    |
|  |  Groq API   |  llama-3.3-70b-versatile                         |
|  |  (stream)   |  Respuesta en tiempo real (opcional)              |
|  +------+-------+                                                    |
|         |                                                            |
|         v                                                            |
|  +--------------+                                                    |
|  |  Respuesta   |  Formateada con identificadores legibles:        |
|  |  Final       |  [RTF N° 09457-5-2004 | Tribunal Fiscal]        |
|  +--------------+                                                    |
|                                                                     |
+--------------------------------------------------------------------+

+--------------------------------------------------------------------+
|                    FASE 0: INGESTA (OFFLINE)                        |
+--------------------------------------------------------------------+
|                                                                     |
|  64,186 HTMLs                                                       |
|  (Jurisprudencia/)                                                  |
|     |                                                               |
|     v                                                               |
|  +------------------+                                               |
|  |  BeautifulSoup   |  Extrae texto visible del HTML               |
|  |  + Limpieza      |  Elimina script, style, head                 |
|  +--------+---------+                                               |
|           |                                                         |
|           v                                                         |
|  +------------------+                                               |
|  |  Groq Batch API  |  Llama 3 (8B o 70B) extrae entidades:       |
|  |  (una vez)       |  hechos, problema, fallo, jueces, leyes      |
|  +--------+---------+                                               |
|           |                                                         |
|           v                                                         |
|  +------------------+     +------------------+                      |
|  |  FAISS Index     |     |  NetworkX Graph  |                     |
|  |  (4500 vectores) |     |  (21732 nodos)   |                     |
|  |  Busq. semantica |     |  Relaciones      |                     |
|  +------------------+     +------------------+                      |
|           |                                                         |
|           v                                                         |
|  +------------------+                                               |
|  |  Metadata JSON   |  Extraccion directa de HTMLs (regex):        |
|  |  (64K registros) |  RTF N°, CAS. N°, EXP. N°, organo, fecha    |
|  +------------------+                                               |
|                                                                     |
+--------------------------------------------------------------------+


## Estructura de Directorios

```
ResumenTokensJurisprudencias/
|
|-- graphrag_console.py        # [USAR] CLI principal: consultas al sistema
|-- .env                       # Config: GROQ_API_KEY, rutas, modelo
|-- README.md                  # Documentacion del proyecto
|-- requirements.txt           # Dependencias Python
|
|-- Jurisprudencia/            # [DATOS] 64,186 HTMLs fuente
|
|-- data/
|   |-- indices/
|   |   |-- faiss_index.bin    # Indice FAISS (busqueda semantica)
|   |   |-- faiss_meta.pkl     # Metadatos de chunks FAISS
|   |   |-- graph_juris.pkl    # Grafo NetworkX serializado
|   |   |-- bm25_index_pro.pkl # Indice BM25 (keyword search)
|   |-- metadata_docs.json     # [GENERADO] Identificadores legibles de HTMLs
|   |-- 15_preguntas_abogado.txt
|   |-- resultados_15_preguntas.txt
|
|-- data_raw/                  # [ARCHIVO] JSON/JSONL de la ingesta Groq
|
|-- scripts/
|   |-- data_prep/
|   |   |-- extraer_metadata_html.py   # [USAR] Extrae metadatos de 64K HTMLs
|   |   |-- preparar_batch_graphrag.py # [ARCHIVO] Preparo lotes para Groq Batch
|   |-- batch_test_suite.sh            # [USAR] Suite automatica de consultas
|   |-- groq_automation/              # [ARCHIVO] Automatizacion de API Groq
|   |-- admin/                        # [ARCHIVO] Scripts de administracion
|   |-- calculators/                  # [ARCHIVO] Calculadoras y benchmarks
|
|-- _archive/                  # Scripts no activos pero preservados
|   |-- groq_automation/       # Subida de lotes, monitoreo, descarga
|   |-- admin/                 # Duplicados, status, debug
|   |-- calculators/           # Proyecciones, simulaciones
|   |-- tests/                 # Tests unitarios (no actualizados)
|   |-- frontend/              # UI Next.js (desacoplada)
|
|-- core/                      # [USAR] Modulos reutilizables
|   |-- config.py              # Configuracion centralizada
|   |-- embedding.py           # Modelo de embeddings
|   |-- llm_clients.py         # Clientes LLM (Groq, DeepSeek)
|
|-- retrieval/                 # [USAR] Logica de recuperacion
|   |-- graph_search.py        # Traversal de grafo
|   |-- hybrid_search.py       # Busqueda hibrida FAISS + BM25
|
|-- pipeline/
|   |-- indexer.py             # Procesamiento de documentos
|
|-- utils/
|   |-- logger_utils.py        # Logging
|   |-- sanitizers.py          # Limpieza de texto
|
|-- docs/                      # Documentacion tecnica
|   |-- ARQUITECTURA.md        # Este archivo
|
|-- tests/                     # Tests
|   |-- test_groq_api.py
|   |-- test_hybrid_tasayco.py
|   |-- ...
|
|-- consultas_guardadas/       # Resultados de consultas previas
|-- logs/                      # Logs del sistema
|-- resultados_benchmark/      # Benchmarks de modelos
+-- backups/                   # Backups
```


## Flujo de una Consulta (Paso a Paso)

### Cuando un abogado pregunta:

```
PREGUNTA: "que dice la jurisprudencia sobre el despido arbitrario"
```

### Paso 1: Embedding + FAISS (0.2s)
1. La pregunta se convierte en vector (384 dims) usando SentenceTransformer
2. FAISS busca los 15 chunks semanticamente mas cercanos
3. Se seleccionan hasta 3 documentos distintos (diversidad)

### Paso 2: Grafo + Metadata (0.1s)
4. Para cada documento, NetworkX recupera sus conexiones:
   - Jueces que lo resolvieron
   - Leyes que cita
   - Partes (demandante/demandado)
5. Metadata se consulta: filename -> "CAS. N° 517-2016-ICA | Corte Suprema"

### Paso 3: Prompt + LLM (3-4s)
6. Se construye el prompt con contexto estructurado
7. El LLM (Groq) decide si los documentos son RELEVANTES o NO
8. Escenario A (datos relevantes): respuesta analitica en 4 partes
9. Escenario B (sin datos): respuesta concisa mostrando que SI se encontro

### Paso 4: Entrega (0s)
10. La respuesta se imprime en consola con formato claro
11. Opcional: streaming palabra por palabra


## Decisiones Arquitectonicas

| Decision | Por que |
|----------|---------|
| FAISS + BM25 hibrido | FAISS para semantica, BM25 para keywords exactas |
| NetworkX para grafo | Ligero, serializable, sin BD externa |
| Solo 3 documentos al LLM | Limita tokens de entrada, evita ruido |
| Groq (no DeepSeek) | Mas rapido, 200 tok/s gratis |
| Metadata desde HTML | Sin re-procesar via API, costo cero |
| Prompt condicional A/B | Evita respuestas infladas en casos negativos |
| Archivos .json para indices | Portatil, sin Docker, sin servicios externos |


## Modelo de Datos

### Documento en FAISS:
```
{
    "id_documento": "408739.html",       # filename
    "chunk_index": 0,                     # orden del chunk
    "chunk_text": "HECHOS: ... FALLO: ..." # texto vectorizado
}
```

### Nodo en Grafo:
```
{
    "408739.html": {                      # key = filename
        "tipo": "Documento",
        "fallo": "El Tribunal Fiscal revoco...",
        "ruta": "/Jurisprudencia/408739.html"
    },
    "Juez:Caller Ferreyros": {
        "tipo": "Juez",
        "nombre": "Caller Ferreyros"
    }
}
```

### Metadata Legible:
```
{
    "408739.html": {
        "identificador": "RTF N° 09457-5-2004",
        "organo": "Tribunal Fiscal",
        "fecha": "Lima, 2 de diciembre de 2004",
        "materia": "Impuesto a la Renta y Multas",
        "tipo": "Resolucion TF"
    }
}
```
