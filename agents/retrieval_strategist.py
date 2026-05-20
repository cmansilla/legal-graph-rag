"""
RETRIEVAL STRATEGIST AGENT — Estrategia de Recuperación Adaptativa
==================================================================
Analiza la consulta y determina los parámetros óptimos de retrieval:
- top_k dinámico (3-15) según complejidad
- modo de recuperación (híbrido, semántico, léxico, web)
- profundidad de exploración del grafo
- uso de HyDE

Fase 2 del plan multi-agente.
"""
import re
from core.llm_clients import groq_client
from core.config import logger


# Estrategia por defecto (cuando no hay LLM disponible)
DEFAULT_STRATEGY = {
    "top_k": 7,
    "retrieval_mode": "hybrid",
    "top_k_mult": 3,
    "k_rrf": 60,
    "use_graph": True,
    "graph_depth": 2,
    "hyde_enabled": True,
    "complexity": "media",
    "reasoning": "Estrategia predeterminada (LLM no disponible)"
}


class RetrievalStrategist:
    """
    Analiza la consulta y produce una estrategia de recuperación adaptativa.

    Uso:
        strategist = RetrievalStrategist()
        strategy = strategist.analyze(query, decision, hyde_query)
        # strategy = {
        #     "top_k": 10,
        #     "retrieval_mode": "hybrid",
        #     "top_k_mult": 4,
        #     ...
        # }
    """

    def __init__(self):
        self._stats = {"total": 0, "llm_calls": 0, "fallback_rules": 0}

    def analyze(self, query, decision="LOCAL", hyde_query=None):
        """
        Analiza la consulta y retorna una estrategia de recuperación.
        Híbrido: reglas duras para casos claros + LLM para casos ambiguos.

        Args:
            query: str — consulta original del usuario
            decision: str — decisión del router (LOCAL/WEB)
            hyde_query: str — query expandida por HyDE (opcional)

        Returns:
            dict — estrategia con parámetros de retrieval
        """
        self._stats["total"] += 1

        if "WEB" in decision:
            return self._strategy_web(query)

        # PASO 1: Reglas duras (sin LLM)
        hard = self._apply_hard_rules(query)
        if hard:
            self._stats["fallback_rules"] += 1
            return hard

        # PASO 2: Solo casos ambiguos → LLM
        strategy = self._analyze_with_llm(query, hyde_query)
        if strategy:
            self._stats["llm_calls"] += 1
            return strategy

        # PASO 3: Fallback final
        self._stats["fallback_rules"] += 1
        return self._analyze_heuristic(query)

    def _apply_hard_rules(self, query):
        """
        Reglas determinísticas para casos claros.
        Retorna strategy o None si el caso es ambiguo.
        """
        q = query.lower()
        words = q.split()
        wc = len(words)

        # --- REGLA 1: Estadística (siempre, sin importar longitud) ---
        estadistica_keywords = [
            "cuántos", "cuantas", "cuál es el", "cuáles son", "qué juez",
            "más casos", "más citada", "más demandada", "frecuencia",
            "estadística", "conteo", "cantidad de", "número de",
            "ranking", "top", "juez que más", "ley más",
            "que juez", "que entidad", "que tribunal",
            "mas sentencias", "mas carga", "mas demandado",
            "mas citadas", "mas casos",
            "mas demandada", "mas frecuente", "mas litigada",  # variantes sin acento
        ]
        if any(kw in q for kw in estadistica_keywords):
            return {
                "top_k": 12, "retrieval_mode": "hybrid", "top_k_mult": 4,
                "k_rrf": 60, "use_graph": True, "graph_depth": 2,
                "hyde_enabled": True, "complexity": "estadistica",
                "reasoning": f"Regla: keyword estadística detectada ({wc} palabras)"
            }

        # --- REGLA 2: Simple (< 7 palabras) ---
        if wc < 7:
            return {
                "top_k": 4, "retrieval_mode": "hybrid", "top_k_mult": 2,
                "k_rrf": 60, "use_graph": False, "graph_depth": 1,
                "hyde_enabled": True, "complexity": "simple",
                "reasoning": f"Regla: consulta corta ({wc} palabras, <7): top_k reducido, sin grafo"
            }

        # --- REGLA 2b: Comparativa (keyword "comparar" + >= 7 palabras) ---
        compara_keywords = ["comparar", "diferencia entre", "comparación", "versus", "vs "]
        if any(kw in q for kw in compara_keywords) and wc >= 7:
            return {
                "top_k": 10, "retrieval_mode": "hybrid", "top_k_mult": 4,
                "k_rrf": 60, "use_graph": True, "graph_depth": 2,
                "hyde_enabled": True, "complexity": "compleja",
                "reasoning": f"Regla: consulta comparativa ({wc} palabras): top_k alto, grafo profundo"
            }

        # --- REGLA 2c: " y " conector de conceptos (7-14 palabras, sin ser compleja) = media ---
        if " y " in q and 7 <= wc < 15:
            return {
                "top_k": 7, "retrieval_mode": "hybrid", "top_k_mult": 3,
                "k_rrf": 60, "use_graph": True, "graph_depth": 1,
                "hyde_enabled": True, "complexity": "media",
                "reasoning": f"Regla: múltiples conceptos con 'y' ({wc} palabras): top_k medio, grafo somero"
            }

        # --- REGLA 3: Compleja (>= 15 palabras) ---
        if wc >= 15:
            return {
                "top_k": 11, "retrieval_mode": "hybrid", "top_k_mult": 4,
                "k_rrf": 60, "use_graph": True, "graph_depth": 2,
                "hyde_enabled": True, "complexity": "compleja",
                "reasoning": f"Regla: consulta larga ({wc} palabras, >=15): top_k alto, grafo profundo"
            }

        # --- CASO AMBIGUO: 7-15 palabras, sin keywords claros ---
        return None  # El LLM decide

    def _analyze_with_llm(self, query, hyde_query=None):
        """Usa un LLM pequeño para clasificar la consulta y definir estrategia."""
        try:
            if not groq_client:
                return None

            text_to_analyze = hyde_query or query
            json_schema = """{
  "complexity": "simple|media|compleja|estadistica",
  "top_k": <3-15, numero de documentos a recuperar>,
  "retrieval_mode": "hybrid|semantic_only|lexical_only",
  "top_k_mult": <2-5, multiplicador de chunks a recuperar por fuente>,
  "use_graph": true|false,
  "graph_depth": <1-2, profundidad de exploracion del grafo>,
  "reasoning": "<explicacion breve de la estrategia>"
}"""
            prompt = (
                "Eres un estratega de recuperacion RAG. Clasifica esta consulta."
                " (CASO AMBIGUO: 7-15 palabras, no es estadistica)\n\n"
                f"CONSULTA: {text_to_analyze}\n\n"
                "SOLO estas 2 opciones:\n"
                "- MEDIA (2 conceptos, 7-15 palabras): top_k=7, top_k_mult=3, use_graph=true, graph_depth=1\n"
                "- SIMPLE (1 concepto, aparentemente simple): top_k=5, top_k_mult=2, use_graph=false\n\n"
                "Responde UNICAMENTE con JSON:\n"
                f"{json_schema}\n"
            )
            # Usar modelo pequeño y rápido para la estrategia
            models = [
                "llama-3.1-8b-instant",
                "mixtral-8x7b-32768"
            ]

            res = None
            for model in models:
                try:
                    res = groq_client.chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.0,
                        max_tokens=300
                    )
                    break
                except Exception:
                    continue

            if not res:
                return None

            raw = res.choices[0].message.content.strip()

            # Extraer JSON del texto (puede venir con markdown)
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0]
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0]

            import json as _json
            strategy = _json.loads(raw.strip())

            # Validar y normalizar
            strategy["top_k"] = max(3, min(15, int(strategy.get("top_k", 7))))
            strategy["top_k_mult"] = max(2, min(5, int(strategy.get("top_k_mult", 3))))
            strategy["graph_depth"] = max(1, min(2, int(strategy.get("graph_depth", 2))))

            if strategy.get("retrieval_mode") not in ("hybrid", "semantic_only", "lexical_only"):
                strategy["retrieval_mode"] = "hybrid"

            strategy["hyde_enabled"] = True
            strategy["k_rrf"] = 60

            logger.info(f"🎯 Strategist: {strategy['complexity']} | "
                        f"top_k={strategy['top_k']} | "
                        f"mode={strategy['retrieval_mode']} | "
                        f"graph={'S'+str(strategy['graph_depth']) if strategy['use_graph'] else 'N'} | "
                        f"{strategy.get('reasoning','')[:60]}")

            return strategy

        except Exception as e:
            logger.warning(f"⚠️ Strategist LLM: {e}")
            return None

    def _analyze_heuristic(self, query):
        """Reglas heurísticas cuando el LLM no está disponible."""
        q = query.lower()
        word_count = len(q.split())
        char_count = len(q)

        # Detectar consultas estadísticas
        estadistica_keywords = [
            "cuántos", "cuantas", "cuál es el", "cuáles son", "qué juez",
            "más casos", "más citada", "más demandada", "frecuencia",
            "estadística", "conteo", "cantidad de", "número de",
            "ranking", "top", "juez que más", "ley más"
        ]
        is_estadistica = any(kw in q for kw in estadistica_keywords)

        # Detectar complejidad por longitud y palabras clave
        is_compleja = word_count >= 15
        is_media = " y " in q and word_count >= 7 or word_count >= 8
        is_simple = word_count < 7

        # Palabras clave que sugieren búsqueda semántica (conceptos abstractos)
        semantico_keywords = [
            "principio", "tendencia", "diferencia", "comparación",
            "concepto", "definición", "fundamento"
        ]
        is_semantico = any(kw in q for kw in semantico_keywords)

        # Palabras clave que sugieren búsqueda léxica (términos concretos)
        lexico_keywords = [
            "artículo", "código", "ley nº", "decreto", "n°",
            "plazo", "requisito", "procedimiento"
        ]
        is_lexico = any(kw in q for kw in lexico_keywords)

        if is_estadistica:
            return {
                "top_k": 12,
                "retrieval_mode": "hybrid",
                "top_k_mult": 4,
                "k_rrf": 60,
                "use_graph": True,
                "graph_depth": 2,
                "hyde_enabled": True,
                "complexity": "estadistica",
                "reasoning": "Consulta estadística: necesita más documentos y grafo profundo"
            }
        elif is_compleja:
            mode = "semantic_only" if is_semantico else ("lexical_only" if is_lexico else "hybrid")
            return {
                "top_k": 10,
                "retrieval_mode": mode,
                "top_k_mult": 4,
                "k_rrf": 60,
                "use_graph": True,
                "graph_depth": 2,
                "hyde_enabled": True,
                "complexity": "compleja",
                "reasoning": f"Consulta compleja ({word_count} palabras): modo {mode}"
            }
        elif is_media:
            return {
                "top_k": 7,
                "retrieval_mode": "hybrid",
                "top_k_mult": 3,
                "k_rrf": 60,
                "use_graph": True,
                "graph_depth": 2,
                "hyde_enabled": True,
                "complexity": "media",
                "reasoning": "Consulta media: parámetros base"
            }
        else:
            mode = "lexical_only" if is_lexico else "hybrid"
            return {
                "top_k": 5,
                "retrieval_mode": mode,
                "top_k_mult": 2,
                "k_rrf": 60,
                "use_graph": False,
                "graph_depth": 1,
                "hyde_enabled": True,
                "complexity": "simple",
                "reasoning": f"Consulta simple ({word_count} palabras): top_k reducido, sin grafo"
            }

    def _strategy_web(self, query):
        """Estrategia para consultas web."""
        return {
            "top_k": 3,
            "retrieval_mode": "web_only",
            "top_k_mult": 1,
            "k_rrf": 60,
            "use_graph": False,
            "graph_depth": 1,
            "hyde_enabled": False,
            "complexity": "web",
            "reasoning": "Consulta web: no aplica retrieval local"
        }

    def get_stats(self):
        """Estadísticas de uso del strategist."""
        return dict(self._stats)
