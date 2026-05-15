"""
LEX RAG — Motor de Consultas Jurisprudenciales (GraphRAG)
========================================================

QUE HACE:
  Toma una pregunta juridica en lenguaje natural, busca documentos
  relevantes en un corpus de 64K+ resoluciones peruanas usando:
  1. FAISS (busqueda semantica)
  2. NetworkX (grafo de relaciones: jueces, leyes, partes)
  3. Groq LLM (respuesta estructurada con citas)

USO BASICO:
  python graphrag_console.py --query "que dice la jurisprudencia sobre despido arbitrario"

  python graphrag_console.py --query "indemnizacion por despido" --stream

  python graphrag_console.py --ingest   # re-indexar desde JSON fuente

ARQUITECTURA:
  Fase 0 - Ingesta:  HTML -> Groq Batch API -> FAISS + NetworkX + Metadata
  Fase 1 - Retrieve: pregunta -> embedding -> FAISS -> graph traversal
  Fase 2 - Generate: contexto -> prompt condicional -> Groq LLM -> respuesta

DEPENDENCIAS:
  pip install sentence-transformers faiss-cpu networkx groq tiktoken python-dotenv
"""

import os, sys, json, glob, logging, argparse, time
import networkx as nx
import tiktoken
import faiss
import numpy as np
import pickle
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
from groq import Groq

# =============================================================
# CONFIGURACION (via .env o vars de entorno)
# =============================================================
FAISS_INDEX_PATH = os.getenv("FAISS_INDEX_PATH", "data/indices/faiss_index.bin")
FAISS_META_PATH  = os.getenv("FAISS_META_PATH",  "data/indices/faiss_meta.pkl")
GRAPH_PATH       = os.getenv("GRAPH_PATH",       "data/indices/graph_juris.pkl")
METADATA_PATH    = os.getenv("METADATA_PATH",    "data/metadata_docs.json")
GROQ_MODEL       = os.getenv("GROQ_MODEL",       "llama-3.3-70b-versatile")
EMBEDDING_MODEL  = os.getenv("EMBEDDING_MODEL",  "sentence-transformers/distiluse-base-multilingual-cased-v2")
MAX_TOKENS_CTX   = int(os.getenv("MAX_TOKENS",       "6000"))
CHUNK_SIZE       = int(os.getenv("CHUNK_SIZE",       "512"))
CHUNK_OVERLAP    = int(os.getenv("CHUNK_OVERLAP",    "50"))
MAX_NEIGHBORS    = int(os.getenv("MAX_NEIGHBORS_PER_NODE", "5"))

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("LexRAG")

# =============================================================
# INICIALIZACION GLOBAL (se ejecuta una vez al importar)
# =============================================================
load_dotenv()
if not os.environ.get("GROQ_API_KEY"):
    logger.error("Falta GROQ_API_KEY en .env")
    sys.exit(1)

groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])

# --- Embeddings ---
logger.info(f"Cargando modelo de embeddings: {EMBEDDING_MODEL}")
embedder = SentenceTransformer(EMBEDDING_MODEL)
embedding_dim = embedder.get_sentence_embedding_dimension()

# --- FAISS (busqueda semantica vectorial) ---
if os.path.exists(FAISS_INDEX_PATH) and os.path.exists(FAISS_META_PATH):
    faiss_index = faiss.read_index(FAISS_INDEX_PATH)
    with open(FAISS_META_PATH, 'rb') as f:
        faiss_metadata = pickle.load(f)
    logger.info(f"FAISS: {faiss_index.ntotal} vectores indexados")
else:
    faiss_index = faiss.IndexFlatL2(embedding_dim)
    faiss_metadata = []  # lista de dicts: {id_documento, chunk_index, chunk_text}

# --- NetworkX (grafo de relaciones) ---
if os.path.exists(GRAPH_PATH):
    try:
        with open(GRAPH_PATH, 'rb') as f:
            G = pickle.load(f)
        logger.info(f"Grafo: {G.number_of_nodes()} nodos, {G.number_of_edges()} aristas")
    except Exception as e:
        logger.warning(f"Error cargando grafo: {e}")
        G = nx.Graph()
else:
    G = nx.Graph()

# --- Metadata de documentos (identificadores legibles) ---
docs_metadata = {}
if os.path.exists(METADATA_PATH):
    try:
        with open(METADATA_PATH, 'r', encoding='utf-8') as f:
            docs_metadata = json.load(f)
        logger.info(f"Metadata: {len(docs_metadata)} documentos con IDs legibles")
    except Exception as e:
        logger.warning(f"Error cargando metadata: {e}")


def get_doc_label(doc_id):
    """
    Convierte un filename (408739.html) en una etiqueta legible:
      "RTF N° 09457-5-2004 | Tribunal Fiscal | 2 de diciembre de 2004"
    Si no hay metadata, devuelve el filename original como fallback.
    """
    meta = docs_metadata.get(doc_id, {})
    if meta.get("identificador"):
        parts = [meta["identificador"]]
        if meta.get("organo"):
            parts.append(meta["organo"])
        if meta.get("fecha"):
            fecha = meta["fecha"].replace("Lima, ", "")
            parts.append(fecha[:35])
        return " | ".join(parts)
    return doc_id  # fallback


# =============================================================
# UTILIDADES
# =============================================================

def normalize_entity(text):
    """Normaliza nombres de jueces/partes para el grafo."""
    if not text:
        return ""
    text = str(text).strip().lower()
    for prefix in ["dr.", "doctor", "dra.", "magistrado", "magistrada", "juez", "sr.", "sra."]:
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
    return text.title()

def chunk_text(text, chunk_size=512, overlap=50):
    """Divide texto en chunks de N palabras con solapamiento."""
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunks.append(" ".join(words[i:i + chunk_size]))
        i += chunk_size - overlap
    return chunks

def estimate_tokens(text):
    """Estima tokens usando tiktoken (cl100k_base como aproximacion)."""
    try:
        return len(tiktoken.get_encoding("cl100k_base").encode(text))
    except Exception:
        return len(text) // 4


# =============================================================
# FASE 0: INGESTA (construir FAISS + grafo desde JSON)
# =============================================================

def ingest_data(force=False):
    """
    Lee los archivos rag_listo_batch_*.json (generados por Groq Batch API)
    y construye:
      - Indice FAISS con chunks de texto
      - Grafo NetworkX con relaciones (jueces, leyes, partes)
    """
    global faiss_index, faiss_metadata, G

    # Si ya hay datos y no se fuerza, salir
    if faiss_index.ntotal > 0 and G.number_of_nodes() > 0 and not force:
        logger.info("Datos cacheados. Usa --ingest para forzar recarga.")
        return

    if force:
        faiss_index = faiss.IndexFlatL2(embedding_dim)
        faiss_metadata = []
        G = nx.Graph()

    # Buscar archivos fuente
    jsonl_files = glob.glob("data_raw/rag_listo_batch_*.json") or glob.glob("rag_listo_batch_*.json")
    if not jsonl_files:
        logger.error("No se encontraron archivos rag_listo_batch_*.json en data_raw/ ni en raiz")
        sys.exit(1)

    latest_file = max(jsonl_files, key=os.path.getmtime)
    logger.info(f"Ingestando: {latest_file}")

    with open(latest_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    processed_ids = set()
    for idx, doc in enumerate(data):
        doc_id = doc.get("id_documento")
        if not doc_id or doc_id in processed_ids:
            continue
        processed_ids.add(doc_id)

        # Extraer campos
        contenido = doc.get("contenido_a_vectorizar", {})
        hechos   = contenido.get("hechos", "")
        problema = contenido.get("problema", "")
        fallo    = contenido.get("fallo", "")

        # Nodo en el grafo
        G.add_node(doc_id, tipo="Documento", fallo=fallo, ruta=doc.get("ruta_local", ""))

        # Chunking + FAISS
        texto = f"HECHOS: {hechos}\nPROBLEMA: {problema}\nFALLO: {fallo}"
        chunks = chunk_text(texto, CHUNK_SIZE, CHUNK_OVERLAP)
        if chunks:
            embeddings = embedder.encode(chunks)
            faiss.normalize_L2(embeddings)
            faiss_index.add(embeddings)
            for c_idx, c_text in enumerate(chunks):
                faiss_metadata.append({
                    "id_documento": doc_id,
                    "chunk_index": c_idx,
                    "chunk_text": c_text
                })

        # Relaciones del grafo
        meta = doc.get("metadatos_graphrag", {})
        for juez in meta.get("jueces_magistrados", []) or []:
            name = normalize_entity(juez)
            if name:
                G.add_node(f"Juez:{name}", tipo="Juez", nombre=name)
                G.add_edge(doc_id, f"Juez:{name}", relacion="JUZGADO_POR")
        for actor in meta.get("demandantes_accionantes", []) or []:
            name = normalize_entity(actor)
            if name:
                G.add_node(f"Actor:{name}", tipo="Actor", nombre=name)
                G.add_edge(doc_id, f"Actor:{name}", relacion="DEMANDADO_POR")
        for dem in meta.get("demandados_accionados", []) or []:
            name = normalize_entity(dem)
            if name:
                G.add_node(f"Demandado:{name}", tipo="Demandado", nombre=name)
                G.add_edge(doc_id, f"Demandado:{name}", relacion="DEMANDA_A")
        for ley in meta.get("leyes_y_articulos_citados", []) or []:
            name = normalize_entity(ley)
            if name:
                G.add_node(f"Ley:{name}", tipo="Ley", nombre=name)
                G.add_edge(doc_id, f"Ley:{name}", relacion="CITA_LEY")

        if (idx + 1) % 100 == 0:
            logger.info(f"Procesados {idx+1} documentos...")

    # Persistir a disco
    os.makedirs(os.path.dirname(FAISS_INDEX_PATH) or '.', exist_ok=True)
    faiss.write_index(faiss_index, FAISS_INDEX_PATH)
    with open(FAISS_META_PATH, 'wb') as f:
        pickle.dump(faiss_metadata, f)
    with open(GRAPH_PATH, 'wb') as f:
        pickle.dump(G, f)

    logger.info(f"Ingesta completa: FAISS={faiss_index.ntotal} vec, Grafo={G.number_of_nodes()} nod")


# =============================================================
# FASE 1: RECUPERACION (FAISS + Graph Traversal)
# =============================================================

def retrieve_relevant(question, top_k=15, max_docs=3):
    """
    1. Convierte pregunta en vector
    2. Busca en FAISS los top_k chunks mas similares
    3. Agrupa por documento, toma max_docs distintos
    4. Para cada documento, hace traversal de 2 saltos en el grafo

    Retorna:
      resultados_por_documento: {doc_id: chunk_text}
      graph_context_str: texto plano con contexto del grafo
    """
    # Embedding de la pregunta
    q_vec = embedder.encode([question])
    faiss.normalize_L2(q_vec)
    distances, indices = faiss_index.search(q_vec, top_k)

    # Agrupar chunks por documento (hasta max_docs distintos)
    resultados = {}
    for idx_chunk in indices[0]:
        if idx_chunk == -1:
            continue
        meta = faiss_metadata[idx_chunk]
        doc_id = meta['id_documento']
        if doc_id not in resultados:
            resultados[doc_id] = meta['chunk_text']
            if len(resultados) >= max_docs:
                break

    return resultados


def build_graph_context(doc_ids):
    """
    Para cada documento, extrae:
    - Fallo (texto de la decision)
    - Vecinos de 1er salto (jueces, leyes, partes)
    - Vecinos de 2do salto (otros documentos conectados)
    """
    lines = []
    for doc_id in doc_ids:
        if not G.has_node(doc_id):
            continue

        node_data = G.nodes[doc_id]
        label = get_doc_label(doc_id)
        fallo = node_data.get("fallo", "No disponible.")

        lines.append(f"\n--- [{label}] ---")
        lines.append(f"FALLO PRINCIPAL: {fallo}")
        lines.append("RELACIONES (GRAFO):")

        for n1 in G.neighbors(doc_id):
            rel  = G[doc_id][n1].get('relacion', 'ASOCIADO_A')
            tipo = G.nodes[n1].get('tipo', '')
            name = G.nodes[n1].get('nombre', n1)
            lines.append(f"  - {rel} -> {tipo}: {name}")

            # 2do salto
            n2 = [n for n in G.neighbors(n1) if n != doc_id]
            if n2:
                muestras = n2[:MAX_NEIGHBORS]
                lines.append(f"    *(Este {tipo} tambien aparece en: {', '.join(muestras)})*")
                if len(n2) > MAX_NEIGHBORS:
                    lines.append(f"    *(...y {len(n2)-MAX_NEIGHBORS} docs mas)*")

    return "\n".join(lines)


# =============================================================
# FASE 2: GENERACION (Prompt + Groq LLM)
# =============================================================

PROMPT_TEMPLATE = """Actua como un analista jurisprudencial de grado experto.
Responde a la siguiente consulta juridica basandote UNICA y EXCLUSIVAMENTE en el contexto estructurado proporcionado a continuacion.
Este contexto es producto de un motor RAG hibrido e incluye tanto fragmentos literales de los documentos (Contexto Textual) como relaciones topologicas entre entidades (Contexto del Grafo de 1er y 2do grado).

CONTEXTO PROPORCIONADO:
{contexto_raw}

PREGUNTA DEL USUARIO:
{question}

INSTRUCCIONES ANALITICAS:

PRIMERO, determina si los documentos recuperados guardan RELACION DIRECTA con la pregunta del usuario o no.

--- ESCENARIO A: DOCUMENTOS RELEVANTES ---
Si los documentos del contexto SI guardan relacion con la pregunta, organiza tu respuesta en:
  (a) Sintesis resolutiva: responde directamente a la cuestion planteada.
  (b) Analisis de evidencias textuales: cita y analiza los fragmentos recuperados, citando SIEMPRE el FALLO (parte resolutiva) de cada documento.
  (c) Analisis de conexiones del grafo: usa las relaciones topologicas identificadas (jueces recurrentes, leyes invocadas, vinculos entre partes) para enriquecer el analisis.
  (d) Conclusion jurisprudencial: sintesis final con valor practico y aplicable al litigio.

--- ESCENARIO B: DOCUMENTOS NO RELEVANTES O INEXISTENTES ---
Si los documentos del contexto NO guardan relacion con la pregunta (tratan otra materia, otro tema), responde de forma CONCISA con esta estructura reducida:
  1. Declaracion clara: "No se encontro jurisprudencia en el corpus analizado que resuelva directamente [tema de la pregunta]."
  2. Documentos recuperados: lista los IDs de los documentos encontrados (si los hubo) con su respectivo TEXTO DEL FALLO (parte resolutiva), aunque traten materia distinta.
  3. Explicacion: indica brevemente que materia o tema tratan los documentos recuperados y por que no responden a la pregunta formulada.

--- REGLAS OBLIGATORIAS (AMBOS ESCENARIOS) ---
1. CITA EL FALLO: Es OBLIGATORIO citar o parafrasear el texto del "FALLO PRINCIPAL" de CADA documento que menciones. El fallo es la parte resolutiva de la resolucion judicial o administrativa y debe ser el nucleo de tu analisis.
2. RIGOR CITACIONAL: Los documentos incluyen identificadores legibles como "RTF N° XXXX", "CAS. N° XXXX", "EXP. N° XXXX". USA esos identificadores en tus citas. Ejemplo: "[CAS. N° 517-2016-ICA | Corte Suprema] -- FALLO: ...".
3. RACIOCINIO DEDUCTIVO en escenario A: Conecta los nodos del grafo de forma explicita en tu argumentacion.
4. NO INVENTES: No postules hechos ni citas que no esten en el contexto proporcionado.
5. LENGUAJE: Manten un registro dialectico formal y tecnologico, propio de las altas cortes procesales.
6. SE CONCISO EN ESCENARIO B: Cuando no haya datos relevantes, responde en maximo 3-4 parrafos. No alargues artificialmente la respuesta.
"""


def query_graphrag(question, stream=False):
    """
    Pipeline completo de consulta:
    Retrieve (FAISS + Grafo) -> Build context -> Generate (Groq)
    """
    logger.info(f"Consultando: '{question[:80]}...'")

    if faiss_index.ntotal == 0:
        print("Base de datos vacia. Ejecuta --ingest primero.")
        return

    # --- Retrieve ---
    resultados = retrieve_relevant(question)

    if not resultados:
        print("No se encontraron documentos relevantes en la base de datos.")
        return

    doc_ids = list(resultados.keys())

    # --- Build context ---
    graph_ctx = build_graph_context(doc_ids)

    ctx = "=== TEXTOS RECUPERADOS ===\n"
    for doc_id, txt in resultados.items():
        ctx += f" [{get_doc_label(doc_id)}] {txt}\n"
    ctx += "\n=== CONTEXTO DEL GRAFO ===\n"
    ctx += graph_ctx

    # --- Build prompt ---
    prompt = PROMPT_TEMPLATE.format(contexto_raw=ctx, question=question)

    # Si excede tokens, recortar priorizando el grafo
    if estimate_tokens(prompt) > MAX_TOKENS_CTX:
        logger.warning("Prompt excede limite de tokens. Priorizando contexto del grafo.")
        ctx_reduced = "=== CONTEXTO DEL GRAFO (PRIORIZADO) ===\n" + graph_ctx
        prompt = f"""Actua como analista jurisprudencial. Basandote en el grafo:
{ctx_reduced}

PREGUNTA: {question}

Usa deduccion multi-salto, cita IDs explicitamente, tono formal."""

    # --- Generate ---
    try:
        print("\n" + "=" * 60)
        print("[RESPUESTA GRAPHRAG]")
        print("=" * 60)

        if stream:
            # Streaming: palabras aparecen en tiempo real
            respuesta = ""
            sys.stdout.flush()
            for chunk in groq_client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "Eres un analista juridico senior experto en hermenutica legal y deduccion logica de redes complejas (GraphRAG)."},
                    {"role": "user", "content": prompt}
                ],
                model=GROQ_MODEL,
                stream=True,
            ):
                if chunk.choices[0].delta.content:
                    palabra = chunk.choices[0].delta.content
                    respuesta += palabra
                    print(palabra, end="", flush=True)
            print()  # newline al final
        else:
            # Normal: espera la respuesta completa
            completion = groq_client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "Eres un analista juridico senior, experto en hermenutica legal y deduccion logica de redes complejas (GraphRAG)."},
                    {"role": "user", "content": prompt}
                ],
                model=GROQ_MODEL,
            )
            respuesta = completion.choices[0].message.content
            print(respuesta)

        print("=" * 60 + "\n")

    except Exception as e:
        logger.error(f"Error con Groq API: {e}")
        if "400" in str(e).lower() or "spend_limit" in str(e).lower():
            print("\n" + "=" * 60)
            print("[AVISO] Limite de cuota/facturacion de Groq alcanzado.")
            print("Mostrando contexto recuperado localmente:")
            print("=" * 60)
            print(ctx)
            print("=" * 60 + "\n")


# =============================================================
# MAIN
# =============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Lex RAG — Motor de Consultas Jurisprudenciales (GraphRAG)",
        epilog="Ejemplo: python graphrag_console.py --query \"despido arbitrario\" --stream"
    )
    parser.add_argument('--ingest', action='store_true',
                        help='Re-construye el indice FAISS y el grafo desde los archivos JSON fuente')
    parser.add_argument('--query', type=str,
                        help='Consulta directa (una pregunta). Omite para modo interactivo')
    parser.add_argument('--stream', action='store_true',
                        help='Activa streaming: las palabras aparecen en tiempo real')

    args = parser.parse_args()

    print("Iniciando Lex RAG (GraphRAG)...")
    ingest_data(force=args.ingest)

    if args.query:
        query_graphrag(args.query, stream=args.stream)
    else:
        # Modo interactivo
        print("\n[Lex RAG Listo]. Escribe '\\q' para salir")
        while True:
            try:
                q = input("\n[?] Tu pregunta juridica: ").strip()
                if q.lower() == '\\q':
                    break
                if q:
                    query_graphrag(q, stream=args.stream)
            except KeyboardInterrupt:
                break
