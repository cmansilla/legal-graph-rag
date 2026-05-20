import pickle
from core.config import GRAPH_PATH, JURISPRUDENCIA_DIR, logger

def get_graph_context(doc_ids):
    audit = {
        "doc_ids_input": doc_ids,
        "nodes_with_data": [],
        "neighbors_found": [],
        "total_edges_processed": 0
    }
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
            node_entry = {
                "doc_id": n,
                "fallo": G.nodes[n].get('fallo', '')[:200],
                "neighbors": []
            }
            contexto_grafo += f"\n--- [{n}] ({JURISPRUDENCIA_DIR}/{n}) ---\n"
            contexto_grafo += f"FALLO: {G.nodes[n].get('fallo', '')}\n"
            contexto_grafo += "VÍNCULOS JURISPRUDENCIALES DIRECTOS:\n"
            for adj in G.neighbors(n):
                rel = G[n][adj].get('relacion', 'RELACIONADO')
                contexto_grafo += f"  - {rel} -> {adj}\n"
                node_entry["neighbors"].append({"node": adj, "relation": rel})
                audit["total_edges_processed"] += 1

                if adj not in processed_nodes:
                    processed_nodes.add(adj)
                    hop2_neighbors = [h for h in G.neighbors(adj) if G.nodes[h].get('tipo') == 'Documento' and h != n]
                    if hop2_neighbors:
                        muestra = hop2_neighbors[:4]
                        contexto_grafo += f"    *(Esta entidad legal vincula colateralmente con: {', '.join(muestra)})*\n"
                        node_entry["neighbors"][-1]["hop2_docs"] = muestra
            audit["nodes_with_data"].append(node_entry)
        else:
            audit["nodes_with_data"].append({"doc_id": n, "not_in_graph": True})

    audit["neighbors_found"] = list(processed_nodes)
    return contexto_grafo, audit
