import os
import argparse
import asyncio
import json
import time
import sys
from agents.router import route_query_and_hyde
from agents.synthesizer import generate_rag_synthesis
from retrieval.web_search import serper_search
from retrieval.hybrid_search import get_hybrid_context
from core.config import logger
from pipeline.indexer import ingest_data, FAISS_INDEX_PATH
from agents.critic import CriticAgent
from agents.retrieval_strategist import RetrievalStrategist
from agents.graph_analyst import GraphAnalyst

# Instancias globales (lazy loading)
_critic = None
_strategist = None
_graph_analyst = None

def get_critic():
    global _critic
    if _critic is None:
        _critic = CriticAgent()
    return _critic

def get_strategist():
    global _strategist
    if _strategist is None:
        _strategist = RetrievalStrategist()
    return _strategist

def get_graph_analyst():
    global _graph_analyst
    if _graph_analyst is None:
        _graph_analyst = GraphAnalyst()
    return _graph_analyst

async def run_console_query(query: str, history=None):
    """Ejecuta una consulta. Retorna (response_text, follow_up_questions, history_actualizado)."""
    logger.info("🧠 Evaluando Query Localmente...")
    
    if history is None:
        history = []
    
    decision, hyde = route_query_and_hyde(query, history)
    
    hybrid_audit = None
    graph_audit = None
    top_docs = None
    web_context = ""
    start_time = time.time()
    
    if "WEB" in decision:
        logger.info("🌐 Router: Consulta de Evento Externo. Buscando en Web...")
        web_context = serper_search(query)
        text_context = ""
        graph_context = ""
        strategy = get_strategist()._strategy_web(query)
    else:
        logger.info("📚 Router: Consulta Legal. Extrayendo Contexto Local Híbrido...")
        # Retrieval Strategist: define parámetros adaptativos
        strategy = get_strategist().analyze(query, decision, hyde)
        logger.info(f"🎯 Estrategia: {strategy['complexity']} | top_k={strategy['top_k']} | "
                    f"mode={strategy['retrieval_mode']} | graph={'S'+str(strategy['graph_depth']) if strategy['use_graph'] else 'N'}")
        top_docs, text_context, hybrid_audit = get_hybrid_context(hyde, top_k=5, strategy=strategy)
        logger.info("🕸️ Extrayendo Referencias Topológicas (Grafo)...")
        if strategy.get("use_graph", True):
            graph_context, graph_audit = get_graph_analyst().analyze(top_docs, query)
        else:
            graph_context = "=== ANÁLISIS DE PRECEDENTES Y CONEXIONES ===\n(Sin contexto de grafo para esta consulta simple)"
            graph_audit = {"doc_ids_input": top_docs, "skipped": True, "reasoning": strategy.get("reasoning", "consulta simple")}
        
    print("\n\n" + "★"*80)
    print("🏛️ MAGISTRADO IA (Stream Modular):")
    print("★"*80)
    
    elapsed = time.time() - start_time
    
    # Consume el generador asíncrono
    respuesta_completa = ""
    follow_up_preguntas = []
    
    async for chunk_str in generate_rag_synthesis(
        query=query,
        decision=decision,
        hyde_query=hyde,
        web_context=web_context if "WEB" in decision else "",
        hybrid_context=text_context if "WEB" not in decision else "",
        graph_context=graph_context if "WEB" not in decision else "",
        history=history,
        hybrid_audit=hybrid_audit,
        graph_audit=graph_audit,
        elapsed=elapsed
    ):
        try:
            # Los datos vienen formados como json string escapado dentro de un dict
            obj = json.loads(chunk_str["data"])
            if obj.get("type") == "chunk":
                print(obj["content"], end="", flush=True)
                respuesta_completa += obj["content"]
            elif obj.get("type") == "follow_up":
                follow_up_preguntas = obj.get("content", [])
            elif obj.get("type") == "info":
                pass # Silenciar los logs de info de streaming en consola para limpieza
        except Exception:
            pass # [DONE] message
            
    print("\n" + "★"*80 + "\n")
    
    # === FEEDBACK LOOP: Critic → Re-escritura ===
    MAX_FEEDBACK_ITER = 2
    feedback_iter = 0
    critic_verdict = None
    context_doc_ids = top_docs if "WEB" not in decision else None
    
    while feedback_iter < MAX_FEEDBACK_ITER:
        feedback_iter += 1
        if not respuesta_completa or len(respuesta_completa) < 100:
            break
        
        critic_verdict = None
        try:
            critic = get_critic()
            critic_verdict = critic.verify(
                respuesta_completa,
                context_doc_ids=context_doc_ids,
                strict=(feedback_iter > 1)  # strict en la 2da iteración
            )
        except Exception as e:
            logger.warning(f"⚠️ Critic: error en verificación: {e}")
            break
        
        # Guardar veredicto en audit (siempre, incluso si no hay error)
        _save_critic_to_audit(critic_verdict)
        
        # Mostrar resultados del crítico
        if critic_verdict and not critic_verdict.passed:
            vd = critic_verdict.to_dict()
            print("🔍 CRÍTICO DE CITAS:")
            for err in critic_verdict.errors:
                print(f"   ⚠️ {err}")
            for w in critic_verdict.warnings:
                print(f"   💡 {w}")
            parts = [f"📊 {vd['total_citations']} citas"]
            if vd['verified']: parts.append(f"✅ {vd['verified']} verificadas")
            if vd['hallucinated']: parts.append(f"⚠️ {vd['hallucinated']} sospechosas")
            if vd['unverifiable']: parts.append(f"❓ {vd['unverifiable']} no verificables")
            parts.append(f"score: {critic_verdict.score:.0%}")
            print(f"   {' · '.join(parts)}")
        
        # Decidir si re-escribir
        if not _needs_rewrite(critic_verdict):
            break  # Sin alucinaciones reales → salir del loop
        
        if feedback_iter >= MAX_FEEDBACK_ITER:
            print("   ⚠️ Límite de correcciones alcanzado. La respuesta se entrega con las advertencias mostradas.")
            break
        
        # Re-escribir
        print(f"\n🔄 Corrigiendo citas sospechosas (intento {feedback_iter}/{MAX_FEEDBACK_ITER})...")
        sys.stdout.flush()
        
        correccion = _rewrite_response(
            query=query,
            respuesta_original=respuesta_completa,
            errores=critic_verdict.errors,
            contexto=text_context if "WEB" not in decision else web_context
        )
        
        if correccion and len(correccion) > 50:
            # Mostrar solo las partes corregidas
            print("   ✅ Corrección aplicada. Nuevas secciones:\n")
            # Encontrar diferencias: mostrar solo lo que cambió
            print(correccion[:500] + ("..." if len(correccion) > 500 else ""))
            print()
            respuesta_completa = correccion  # Reemplazar para próxima iteración
        else:
            print("   ⚠️ No se pudo corregir automáticamente.")
            break
    
    else:
        # Solo si el while terminó sin break (máximas iteraciones)
        if critic_verdict and not critic_verdict.passed:
            vd = critic_verdict.to_dict()
            if vd['hallucinated'] > 0:
                print(f"   ⚠️ Límite de correcciones alcanzado ({MAX_FEEDBACK_ITER}). Se entrega con advertencias.")
    
    # Mostrar preguntas de seguimiento si hay
    if follow_up_preguntas:
        print("💡 Preguntas de seguimiento sugeridas:")
        for i, q in enumerate(follow_up_preguntas, 1):
            print(f"   [{i}] {q}")
        print("   [0] Continuar sin repregunta")
        print()
    
    # Actualizar historial (últimos 3 intercambios máximo)
    if respuesta_completa:
        history.append({"role": "user", "content": query})
        history.append({"role": "assistant", "content": respuesta_completa[:2000]})
        if len(history) > 8:  # 4 exchanges max
            history = history[-8:]
    
    return respuesta_completa, follow_up_preguntas, history


# ──────────────────────────────────────────────
# FEEDBACK LOOP: Helper functions
# ──────────────────────────────────────────────

def _save_critic_to_audit(critic_verdict):
    """Guarda el veredicto del crítico en el audit JSON más reciente."""
    if not critic_verdict:
        return
    try:
        import glob as _glob
        audit_files = sorted(_glob.glob("consultas_guardadas/*_audit.json"), key=os.path.getmtime)
        if audit_files:
            with open(audit_files[-1], 'r', encoding='utf-8') as f:
                audit_data = json.load(f)
            audit_data["critic"] = critic_verdict.to_dict()
            if "feedback" not in audit_data:
                audit_data["feedback"] = {"iterations": 0, "corrections": []}
            with open(audit_files[-1], 'w', encoding='utf-8') as f:
                json.dump(audit_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"⚠️ No se pudo guardar critic en audit: {e}")


def _needs_rewrite(critic_verdict):
    """
    Determina si el feedback loop debe re-escribir.
    Solo re-escribe si hay hallucinationes REALES (doc_id no existe en corpus).
    No re-escribe por identificadores no verificables (EXP. N°, CAS. N° textuales).
    """
    if not critic_verdict:
        return False
    vd = critic_verdict.to_dict()
    return vd.get("hallucinated", 0) > 0


def _rewrite_response(query, respuesta_original, errores, contexto):
    """
    Pide al LLM que re-escriba la respuesta eliminando citas falsas.
    Usa un modelo rápido (llama-3.1-8b) para la corrección.
    """
    from core.llm_clients import groq_client

    prompt = f"""Eres un asistente legal que debe CORREGIR una respuesta jurídica.
La respuesta original contiene citas a documentos que NO EXISTEN en el corpus.
Debes re-escribir la respuesta eliminando o reemplazando SOLO las citas falsas.
Mantén el resto de la respuesta intacta: estructura, argumentos, citas válidas.

CITAS FALSAS A ELIMINAR:
{chr(10).join(f'- {e}' for e in errores[:5])}

CONTEXTO ORIGINAL (documentos reales):
{contexto[:2000]}

RESPUESTA ORIGINAL (con errores):
{respuesta_original[:3000]}

INSTRUCCIONES:
1. Elimina cualquier referencia a las citas falsas listadas arriba.
2. NO inventes nuevas citas para reemplazarlas.
3. Si una sección quedó vacía al eliminar la cita falsa, reformula esa oración.
4. Mantén el formato, las negritas y la estructura general.
5. Responde SOLO con el texto corregido, sin explicaciones."""

    try:
        res = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=3000
        )
        corrected = res.choices[0].message.content.strip()
        # Limpiar posibles prefijos/sufijos
        if corrected.startswith("```"):
            corrected = corrected.split("```")[1] if "```" in corrected[3:] else corrected[3:]
            if corrected.endswith("```"):
                corrected = corrected[:-3]
        return corrected
    except Exception as e:
        logger.warning(f"⚠️ Feedback: error en re-escritura: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description='Lex RAG Modular (CLI).')
    parser.add_argument('--ingest', action='store_true', help='Fuerza reingesta a los 3 motores (FAISS, BM25, NetworkX).')
    parser.add_argument('--query', type=str, help='Ejecutar sin interactividad.')
    args = parser.parse_args()
    
    if args.ingest:
        ingest_data(force=True)
    elif not os.path.exists(FAISS_INDEX_PATH):
        logger.info("No se encontró base local, auto-ingestando...")
        ingest_data()
        
    if args.query:
        asyncio.run(run_console_query(args.query))
    else:
        print("\n" + "="*50)
        print("  ⚖️ LEX RAG PRO MODULAR (FAISS+BM25+Grafo+LLM)  ")
        print("="*50)
        conversation_history = []
        last_follow_ups = []
        while True:
            try:
                q = input("\n📝 Su Señoría, ingrese la consulta judicial: ").strip()
                if q.lower() == '\\q':
                    break
                # Soporte para repreguntas rápidas: teclear solo el número
                if q.isdigit() and last_follow_ups:
                    idx = int(q)
                    if 1 <= idx <= len(last_follow_ups):
                        q = last_follow_ups[idx - 1]
                        print(f"↳ Repregunta: {q}")
                if q:
                    resp, follow_ups, conversation_history = asyncio.run(
                        run_console_query(q, history=conversation_history)
                    )
                    last_follow_ups = follow_ups
            except KeyboardInterrupt:
                break

if __name__ == "__main__":
    main()
