import asyncio
import json
from core.llm_clients import groq_client
from core.config import logger
from utils.logger_utils import save_query_log, save_chunk_audit

MAX_HISTORY_EXCHANGES = 3  # Mantener solo los últimos 3 intercambios (user+assistant)
MAX_HISTORY_TOKENS = 4000  # Tokens máximos del historial antes de truncar

async def generate_rag_synthesis(query, decision, hyde_query, web_context, hybrid_context, graph_context, history=None, hybrid_audit=None, graph_audit=None, elapsed=None):
    if history is None:
        history = []
        
    if "WEB" in decision:
        contexto_raw = f"=== CONTEXTO WEB ===\n{web_context}"
    else:
        contexto_raw = f"{hybrid_context}\n\n{graph_context}"

    prompt_magistrado = f"""Actúa como un Magistrado de la Corte Suprema y Analista Jurídico de grado experto.
Responde a la siguiente consulta jurídica basándote ÚNICA y EXCLUSIVAMENTE en el contexto recuperado (que incluye fragmentos de sentencias y doctrina relacional).

CONTEXTO RECUPERADO:
{contexto_raw}

PREGUNTA DEL USUARIO: {query}

INSTRUCCIONES CRÍTICAS (DE SEGUIMIENTO OBLIGATORIO):
1. RACIOCINIO DEDUCTIVO Y ESTADÍSTICO (GRAFOS): Utiliza intensivamente la sección 'ANÁLISIS DE PRECEDENTES Y CONEXIONES'. Si la pregunta inquiere sobre frecuencias (ej. "jueces con más casos" o "leyes más citadas"), DEBES contar los vínculos colaterales expuestos (los textos que dicen "x vincula colateralmente con: doc_1, doc_2...") como evidencia plena de cantidad y armar clasificaciones basados en estos nodos. NO te escudes en la falta de texto completo de esos documentos colaterales.
2. LENGUAJE 100% JURÍDICO (PROHIBICIÓN TÉCNICA): Tu estructura de razonamiento debe presentarse como un dictamen constitucional puro. Está estrictamente PROHIBIDO revelar la arquitectura tecnológica que extrajo esta información (jamás digas "grafos", "nodos", "topología", "algoritmos" o "saltos" para explicar cómo obtuviste el dato documental). Sin embargo, si la Litis/Materia del caso (el contenido real de la sentencia) versa sobre temas de informática, tecnología o software, DEBES analizar esos hechos libremente aplicando los términos técnicos del campo que la Ley discute.
3. RIGOR CITACIONAL: Cita invariablemente el identificador legible del documento (RTF N°, CAS. N°, EXP. N°) y la ruta al archivo. Ejemplo: "según **CAS. N° 15-2015 LAMBAYEQUE** (Jurisprudencia/1612215.html)".
4. TONO Y ESTRUCTURA: Adopta un tono profesional, empático y conversacional, como un abogado asesorando a un colega. Estructura tu respuesta libremente en Markdown usando encabezados cortos, negritas y viñetas para que sea fácil de leer, sin necesidad de seguir un formato rígido o robótico.
5. EXHAUSTIVIDAD VS INVENCIÓN: No inventes nombres o casos inexistentes. Si la respuesta requiere contar, debes contar exclusivamente sobre las conexiones documentales presentes en el prompt. Si definitivamente el contexto no provee ningún hilo, declara: "Información insuficiente en el corpus analizado para resolver esta cuestión".
"""

    yield {"data": json.dumps({"type": "info", "content": "🚀 Generando dictamen con Inteligencia Autónoma..."})}
    await asyncio.sleep(0.01)
    
    models_to_try = [
        "moonshotai/kimi-k2-instruct-0905",
        "llama-3.3-70b-versatile",
        "mixtral-8x7b-32768",
        "llama-3.1-8b-instant"
    ]
    
    messages = [{"role": "system", "content": "Eres un Agente RAG Avanzado actuando como Corte Suprema"}]
    
    # Inyectar historial de conversación previo (limitado a los últimos N intercambios)
    if history:
        # Mantener solo los últimos MAX_HISTORY_EXCHANGES intercambios
        trimmed = history[-(MAX_HISTORY_EXCHANGES * 2):]
        # Verificar tokens aproximados del historial
        hist_tokens = sum(len(m.get("content", "")) // 4 for m in trimmed)
        if hist_tokens > MAX_HISTORY_TOKENS:
            # Truncar contenido de mensajes más antiguos si excede
            for m in trimmed[:-1]:
                if len(m.get("content", "")) > 500:
                    m["content"] = m["content"][:500] + "... [truncado]"
        for msg in trimmed:
            messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
        
    # Añadir el prompt actual enriquecido
    messages.append({"role": "user", "content": prompt_magistrado})
    
    ans = ""
    for model_name in models_to_try:
        try:
            response = groq_client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=0.1,
                stream=True
            )
            
            for chunk in response:
                content = chunk.choices[0].delta.content
                if content:
                    ans += content
                    yield {"data": json.dumps({"type": "chunk", "content": content})}
                    await asyncio.sleep(0.01)
            
            break
            
        except Exception as e:
            logger.warning(f"Error con modelo {model_name}: {e}. Intentando failover.")
            continue
            
    if ans:
        save_query_log(query, ans, contexto_raw)

        if hybrid_audit is not None or graph_audit is not None:
            save_chunk_audit(
                query=query,
                hybrid_audit=hybrid_audit,
                graph_audit=graph_audit,
                response=ans,
                decision=decision,
                hyde_query=hyde_query,
                elapsed=elapsed
            )
        
        # Bloque Cuestionador LLaMA-3 (Preguntas de Seguimiento)
        try:
            yield {"data": json.dumps({"type": "info", "content": "💡 Sintetizando hilos de seguimiento..."})}
            await asyncio.sleep(0.01)
            
            follow_up_prompt = f"""Basado en el dictamen legal que acabas de emitir, redacta EXACTAMENTE 3 preguntas breves (máximo 12 palabras cada una) que un usuario podría hacer a continuación para profundizar el análisis.
Retorna ÚNICAMENTE un objeto JSON válido con la siguiente estructura, sin formato Markdown ni saludos:
{{"preguntas": ["Pregunta 1", "Pregunta 2", "Pregunta 3"]}}

Dictamen:
{ans[:2000]}..."""
            
            follow_up_response = groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": follow_up_prompt}],
                temperature=0.3
            )
            raw_json = follow_up_response.choices[0].message.content.strip()
            
            # Simple string cleaning to handle Markdown code blocks
            if raw_json.startswith("```json"):
                raw_json = raw_json[7:]
            if raw_json.startswith("```"):
                raw_json = raw_json[3:]
            if raw_json.endswith("```"):
                raw_json = raw_json[:-3]
                
            parsed_json = json.loads(raw_json.strip())
            questions = parsed_json.get("preguntas", [])
            
            if questions and isinstance(questions, list):
                yield {"data": json.dumps({"type": "follow_up", "content": questions[:3]})}
        except Exception as e:
            logger.warning(f"Error generando follow-ups: {e}")
        
    yield {"data": "[DONE]"}
