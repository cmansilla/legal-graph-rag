from core.llm_clients import groq_client

def route_query_and_hyde(query, history=None):
    if history is None:
        history = []
    
    recent_history = [msg['content'] for msg in history[-4:] if msg['role'] == 'user']
    history_ctx = " | ".join(recent_history) if recent_history else "No hay historial previo."

    """Router Groq ultrarápido para evaluar la query y dar un HyDE"""
    prompt = f"""Eres un Agente Enrutador Legal (Perú). Analiza la siguiente consulta y el historial de la conversación:
Historial reciente del usuario: {history_ctx}
Consulta actual: "{query}"

1. ¿La pregunta exige buscar explícitamente en internet noticias del 2024+, farándula, clima o datos mundiales ajenos a la ley o a un juzgado/entidad? Si y solo si es así, responde 'WEB'.
2. Si es una búsqueda de casos legales, jurisprudencia, expedientes, resoluciones O PREGUNTAS ESTADÍSTICAS sobre entidades, jueces, demandados o tribunales (ej. "entidad más demandada", "tribunal con más carga"), responde 'LOCAL'.

Tu respuesta debe tener exactamente 2 líneas.
LINEA 1: 'WEB' o 'LOCAL'
LINEA 2: Escribe una expansión muy profesional (1 frase) hipotética de la "Consulta actual", integrando el contexto del "Historial reciente" si la consulta se refiere a él (ej. resolviendo pronombres como "él", "esa persona", "ese apellido"). Conserva estrictamente los nombres de personas, empresas, leyes o números. REGLA CRÍTICA: Debes PRESERVAR CUALQUIER NOMBRE PROPIO (Nombres, Apellidos, Empresas) mencionado. ¡Jamás omitas el sustantivo central!
"""
    try:
        if not groq_client: return 'LOCAL', query
        
        models_to_try = [
            "moonshotai/kimi-k2-instruct-0905",
            "llama-3.3-70b-versatile"
        ]
        
        res = None
        for model in models_to_try:
            try:
                res = groq_client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0
                )
                break  # Éxito, rompe el loop de modelos
            except Exception:
                continue

        if not res:
            return 'LOCAL', query

        ans = res.choices[0].message.content.strip()
        lines = [line.strip() for line in ans.split('\n') if line.strip()]
        decision = lines[0].upper() if len(lines) > 0 else 'LOCAL'
        hyde = lines[1] if len(lines) > 1 else query
        return decision, hyde
    except Exception:
        return 'LOCAL', query
