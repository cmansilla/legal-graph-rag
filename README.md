# Lex RAG — Motor de Consultas Jurisprudenciales

**GraphRAG** para jurisprudencia peruana. Busca en 64,186 resoluciones (Tribunal Fiscal, Corte Suprema, Tribunal Constitucional) usando FAISS + NetworkX + Groq LLM.

## ⚡ Uso rápido

```bash
# Consulta directa
python graphrag_console.py --query "despido arbitrario reposicion"

# Con streaming (palabras aparecen en tiempo real)
python graphrag_console.py --query "violencia familiar medidas proteccion" --stream

# Modo interactivo
python graphrag_console.py

# Re-indexar desde JSON fuente
python graphrag_console.py --ingest
```

## Arquitectura

```
Pregunta -> [FAISS] -> docs relevantes -> [NetworkX] -> grafo de relaciones
                                              |
                                              v
                                    [Groq LLM] -> respuesta estructurada
```

3 fases:
1. **Recuperación**: embedding semántico (FAISS) + traversal de grafo (NetworkX)
2. **Prompt condicional**: Escenario A (datos relevantes) o B (sin datos)
3. **Generación**: Groq llama-3.3-70b-versatile con streaming opcional

## Estructura del proyecto

```
LexRAG/
|-- graphrag_console.py       # [USAR] CLI principal
|-- .env                      # GROQ_API_KEY y config
|-- data/
|   |-- indices/              # FAISS + NetworkX pre-indexados
|   |-- metadata_docs.json    # IDs legibles (RTF, CAS, EXP)
|-- scripts/
|   |-- data_prep/            # Preparación de datos
|   |-- batch_test_suite.sh   # Suite automática de tests
|-- docs/
|   |-- ARQUITECTURA.md       # Diagrama detallado del sistema
|-- _archive/                 # Scripts preservados pero no activos
```

## Configuración

Editar `.env`:
```
GROQ_API_KEY=gsk_tu_key_aqui
GROQ_MODEL=llama-3.3-70b-versatile
MAX_TOKENS=6000
```

## Dataset

- **64,186** resoluciones peruanas en HTML
- **4,500** vectores FAISS (subconjunto indexado)
- **21,732** nodos en el grafo (jueces, leyes, partes)
- **Tipos**: Tribunal Fiscal, Corte Suprema (Casación), Tribunal Constitucional

## Licencia

Uso interno — proyecto de investigación jurídica.
