"""
GRAPH ANALYST AGENT — Análisis algorítmico del grafo NetworkX
=============================================================
Sin LLM. Solo conteos, frecuencias y traversal de grafo.
Responde con precisión: ¿qué juez aparece más? ¿qué ley se cita más?
¿qué entidad es más demandada? ¿qué documentos comparten precedentes?

Uso:
    analyst = GraphAnalyst()
    narrative, audit = analyst.analyze(doc_ids, query)
"""
import pickle
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from core.config import GRAPH_PATH, JURISPRUDENCIA_DIR, logger


class GraphAnalyst:
    """
    Analiza el grafo NetworkX para extraer estadísticas y relaciones
    entre documentos, jueces, leyes, actores y demandados.

    Toda la lógica es algorítmica — no usa LLM para los cómputos.
    """

    def __init__(self):
        self._G = None

    # ──────────────────────────────────────────────
    # API pública
    # ──────────────────────────────────────────────

    def analyze(self, doc_ids, query=None):
        """
        Punto de entrada único.

        Args:
            doc_ids: list[str] — documentos recuperados (top_docs)
            query: str — consulta original (opcional, para sesgar análisis)

        Returns:
            (narrative: str, audit: dict)
            Compatible con get_graph_context() del pipeline actual.
        """
        G = self._load()
        if not G:
            return self._empty_result(doc_ids)

        # Paralelizar: colección de entidades y stats en 2 hilos
        with ThreadPoolExecutor(max_workers=2) as pool:
            future_entities = pool.submit(self._collect_entities, G, doc_ids)
            # Mientras se colectan entidades, computamos estadísticas globales
            future_global = pool.submit(self._compute_global_stats, G, doc_ids)

        entities = future_entities.result()
        global_stats = future_global.result()

        # Estadísticas locales (basadas en las entidades de los docs recuperados)
        local_stats = self._compute_local_stats(entities)

        # Cadenas de precedente (documentos que comparten leyes)
        chains = self._find_chains(G, doc_ids)

        # Ensamblar resultado
        narrative = self._format(doc_ids, entities, local_stats, global_stats, chains)
        audit = self._build_audit(doc_ids, entities, local_stats, chains)

        return narrative, audit

    # ──────────────────────────────────────────────
    # Carga del grafo (lazy, una sola vez)
    # ──────────────────────────────────────────────

    def _load(self):
        if self._G is None:
            try:
                with open(GRAPH_PATH, 'rb') as f:
                    self._G = pickle.load(f)
                logger.info(f"🕸️ GraphAnalyst: {self._G.number_of_nodes()} nodos, "
                           f"{self._G.number_of_edges()} aristas")
            except Exception as e:
                logger.warning(f"⚠️ GraphAnalyst: no se pudo cargar grafo: {e}")
                self._G = False  # cache negativo
        return self._G if self._G is not False else None

    # ──────────────────────────────────────────────
    # Colección de entidades (1 doc → N entidades)
    # ──────────────────────────────────────────────

    def _collect_entities(self, G, doc_ids):
        """
        Para cada documento, extrae jueces, leyes, actores y demandados conectados.

        Ejecutado en un hilo separado.
        """
        entities = {}
        for doc in doc_ids:
            if doc not in G:
                continue
            doc_data = {"fallo": G.nodes[doc].get('fallo', '')[:300]}
            grupos = {"jueces": [], "leyes": [], "actores": [], "demandados": []}
            for adj in G.neighbors(doc):
                tipo = G.nodes[adj].get('tipo', '')
                if tipo == 'Juez':
                    grupos["jueces"].append(self._node_info(G, doc, adj))
                elif tipo == 'Ley':
                    grupos["leyes"].append(self._node_info(G, doc, adj))
                elif tipo == 'Actor':
                    grupos["actores"].append(self._node_info(G, doc, adj))
                elif tipo == 'Demandado':
                    grupos["demandados"].append(self._node_info(G, doc, adj))
            doc_data.update(grupos)
            entities[doc] = doc_data
        return entities

    def _node_info(self, G, doc, adj):
        """Info de un nodo vecino: nombre + relación + hop2_docs."""
        rel = G[doc][adj].get('relacion', '')
        name = G.nodes[adj].get('nombre', adj)
        # Hop2: otros documentos conectados a esta misma entidad
        hop2 = [n for n in G.neighbors(adj)
                if G.nodes[n].get('tipo') == 'Documento' and n != doc]
        return {
            "node": adj,
            "relation": rel,
            "name": name,
            "hop2_count": len(hop2),
            "hop2_sample": hop2[:3]
        }

    # ──────────────────────────────────────────────
    # Estadísticas GLOBALES (todo el grafo, no solo los docs recuperados)
    # ──────────────────────────────────────────────

    def _compute_global_stats(self, G, doc_ids):
        """
        Estadísticas sobre el grafo completo relevantes a los doc_ids.
        Se ejecuta en paralelo con _collect_entities.
        """
        # Contar cuántos documentos total hay por entidad relevante
        doc_set = set(doc_ids)
        relevant_entities = set()
        for doc in doc_ids:
            if doc in G:
                for adj in G.neighbors(doc):
                    relevant_entities.add(adj)

        # Total de documentos en el grafo que comparten estas entidades
        shared_counts = {}
        for ent in list(relevant_entities)[:50]:  # limitar a 50 entidades
            if ent in G:
                shared = sum(1 for n in G.neighbors(ent)
                             if G.nodes[n].get('tipo') == 'Documento')
                shared_counts[ent] = shared

        return {
            "total_documentos_grafo": sum(1 for _, d in G.nodes(data=True)
                                          if d.get('tipo') == 'Documento'),
            "entidades_compartidas": shared_counts
        }

    # ──────────────────────────────────────────────
    # Estadísticas LOCALES (solo los docs recuperados)
    # ──────────────────────────────────────────────

    def _compute_local_stats(self, entities):
        """Frecuencias de jueces, leyes, actores, demandados en los docs recuperados."""
        stats = {
            "jueces": Counter(),
            "leyes": Counter(),
            "actores": Counter(),
            "demandados": Counter(),
        }
        for doc, data in entities.items():
            for j in data.get("jueces", []):
                stats["jueces"][j["name"] or j["node"]] += 1
            for l in data.get("leyes", []):
                stats["leyes"][l["name"] or l["node"]] += 1
            for a in data.get("actores", []):
                stats["actores"][a["name"] or a["node"]] += 1
            for d in data.get("demandados", []):
                stats["demandados"][d["name"] or d["node"]] += 1

        return {
            "top_jueces": stats["jueces"].most_common(8),
            "top_leyes": stats["leyes"].most_common(8),
            "top_actores": stats["actores"].most_common(5),
            "top_demandados": stats["demandados"].most_common(5),
            "total_jueces_unicos": len(stats["jueces"]),
            "total_leyes_unicas": len(stats["leyes"]),
        }

    # ──────────────────────────────────────────────
    # Cadenas de precedente
    # ──────────────────────────────────────────────

    def _find_chains(self, G, doc_ids):
        """
        Documentos que comparten jueces o leyes = red de precedente.
        Útil para responder "¿qué otros casos citan la misma ley?"
        """
        chains = defaultdict(list)
        for doc in doc_ids:
            if doc not in G:
                continue
            for adj in G.neighbors(doc):
                tipo = G.nodes[adj].get('tipo', '')
                if tipo not in ('Ley', 'Juez'):
                    continue
                # Otros documentos conectados a esta entidad
                otros = [n for n in G.neighbors(adj)
                         if G.nodes[n].get('tipo') == 'Documento' and n != doc]
                if otros:
                    chains[doc].append({
                        "entidad": adj,
                        "tipo_entidad": tipo,
                        "otros_docs": otros[:5],
                        "total_conexiones": len(otros)
                    })
        return dict(chains)

    # ──────────────────────────────────────────────
    # Formateo de narrativa
    # ──────────────────────────────────────────────

    def _format(self, doc_ids, entities, local_stats, global_stats, chains):
        """Construye el texto legible para el prompt del LLM."""
        lines = ["=== ANÁLISIS DE PRECEDENTES Y CONEXIONES ==="]
        lines.append(f"Documentos analizados: {len(doc_ids)}")

        # ── Fallos ──
        lines.append("")
        lines.append("--- FALLOS DE LOS DOCUMENTOS ---")
        for doc in doc_ids:
            data = entities.get(doc, {})
            fallo = data.get("fallo", "No disponible.")[:300]
            lines.append(f"  [{doc}] ({JURISPRUDENCIA_DIR}/{doc})")
            lines.append(f"    FALLO: {fallo}")

        # ── Jueces ──
        if local_stats["top_jueces"]:
            lines.append("")
            lines.append("--- JUECES QUE HAN INTERVENIDO ---")
            for i, (juez, count) in enumerate(local_stats["top_jueces"], 1):
                lines.append(f"  {i}. {juez} — intervino en {count} caso(s)")

        # ── Leyes ──
        if local_stats["top_leyes"]:
            lines.append("")
            lines.append("--- LEYES CITADAS CON MAYOR FRECUENCIA ---")
            for i, (ley, count) in enumerate(local_stats["top_leyes"], 1):
                lines.append(f"  {i}. {ley} — citada en {count} caso(s)")

        # ── Partes ──
        if local_stats["top_actores"]:
            lines.append("")
            lines.append("--- ACTORES RECURRENTES ---")
            for i, (actor, count) in enumerate(local_stats["top_actores"], 1):
                lines.append(f"  {i}. {actor} — {count} caso(s)")

        if local_stats["top_demandados"]:
            lines.append("")
            lines.append("--- DEMANDADOS RECURRENTES ---")
            for i, (dem, count) in enumerate(local_stats["top_demandados"], 1):
                lines.append(f"  {i}. {dem} — {count} caso(s)")

        # ── Cadenas de precedente ──
        if chains:
            lines.append("")
            lines.append("--- VÍNCULOS ENTRE DOCUMENTOS (PRECEDENTES COMPARTIDOS) ---")
            for doc, vinculos in list(chains.items())[:5]:
                for v in vinculos[:3]:
                    others = ", ".join(v["otros_docs"][:3])
                    lines.append(f"  [{doc}] comparte {v['tipo_entidad']} '{v['entidad']}' "
                                 f"con: {others} (+{v['total_conexiones']-3} más...)")

        # ── Totales ──
        lines.append("")
        lines.append("--- ESTADÍSTICAS DEL GRAFO ---")
        lines.append(f"  Jueces únicos en estos docs: {local_stats['total_jueces_unicos']}")
        lines.append(f"  Leyes únicas citadas: {local_stats['total_leyes_unicas']}")
        lines.append(f"  Total documentos en el grafo: {global_stats['total_documentos_grafo']}")

        return "\n".join(lines)

    # ──────────────────────────────────────────────
    # Auditoría
    # ──────────────────────────────────────────────

    def _build_audit(self, doc_ids, entities, local_stats, chains):
        """Estructura JSON para el audit."""
        return {
            "doc_ids": doc_ids,
            "total_entities_per_doc": {
                doc: {
                    "jueces": len(e.get("jueces", [])),
                    "leyes": len(e.get("leyes", [])),
                    "actores": len(e.get("actores", [])),
                    "demandados": len(e.get("demandados", [])),
                }
                for doc, e in entities.items()
            },
            "top_jueces": local_stats["top_jueces"],
            "top_leyes": local_stats["top_leyes"],
            "top_actores": local_stats["top_actores"],
            "top_demandados": local_stats["top_demandados"],
            "chains_encontradas": len(chains),
            "cadenas": {
                doc: [{"entidad": v["entidad"], "tipo": v["tipo_entidad"],
                       "conexiones": v["total_conexiones"]}
                      for v in vinculos[:5]]
                for doc, vinculos in list(chains.items())[:10]
            }
        }

    def _empty_result(self, doc_ids):
        """Resultado vacío cuando el grafo no está disponible."""
        audit = {"doc_ids": doc_ids, "error": "Grafo no disponible"}
        text = "=== ANÁLISIS DE PRECEDENTES Y CONEXIONES ===\n(Grafo no disponible para este análisis)"
        return text, audit
