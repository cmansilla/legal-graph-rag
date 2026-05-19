import pickle
from core.config import GRAPH_PATH, JURISPRUDENCIA_DIR, logger

def get_graph_context(doc_ids):
    try:
        with open(GRAPH_PATH, 'rb') as f:
            G = pickle.load(f)
    except Exception as e:
        logger.warning(f"No se pudo cargar el grafo: {e}")
        return ""

    contexto_grafo = "=== ANÁLISIS DE PRECEDENTES Y CONEXIONES ===\n"
    processed_nodes = set()

    for n in doc_ids:
        if n in G:
            contexto_grafo += f"\n--- [{n}] ({JURISPRUDENCIA_DIR}/{n}) ---\n"
            contexto_grafo += f"FALLO: {G.nodes[n].get('fallo', '')}\n"
            contexto_grafo += "VÍNCULOS JURISPRUDENCIALES DIRECTOS:\n"
            for adj in G.neighbors(n):
                rel = G[n][adj].get('relacion', 'RELACIONADO')
                contexto_grafo += f"  - {rel} -> {adj}\n"
                
                if adj not in processed_nodes:
                    processed_nodes.add(adj)
                    hop2_neighbors = [h for h in G.neighbors(adj) if G.nodes[h].get('tipo') == 'Documento' and h != n]
                    if hop2_neighbors:
                        muestra = hop2_neighbors[:4]
                        contexto_grafo += f"    *(Esta entidad legal vincula colateralmente con: {', '.join(muestra)})*\n"
    return contexto_grafo
