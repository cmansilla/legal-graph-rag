"""
BATERÍA DE 10 CONSULTAS - Retrieval Strategist + Critic
========================================================
Prueba el Retrieval Strategist Agent con consultas de 
distintos niveles de complejidad y verifica:
- Estrategia elegida (top_k, mode, graph)
- Crítico de citas
- Tiempos de respuesta
"""
import os, sys, json, re, time, subprocess, glob
from datetime import datetime

PROJECT_DIR = "/mnt/d/PyCode/ResumenTokensJurisprudencias"
PYTHON_EXE = "python3"
REPORT_DIR = os.path.join(PROJECT_DIR, "data")
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
REPORT_PATH = os.path.join(REPORT_DIR, f"bateria_strategist_{TIMESTAMP}.txt")

QUERIES = [
    # Simples (top_k esperado: 3-5)
    {"id": "S1", "nivel": "simple", "desc": "Despido arbitrario",
     "query": "despido arbitrario"},
    {"id": "S2", "nivel": "simple", "desc": "Nulidad de cosa juzgada",
     "query": "nulidad de cosa juzgada fraudulenta"},
    # Medias (top_k esperado: 5-8)
    {"id": "M1", "nivel": "media", "desc": "Reposición + desnaturalización",
     "query": "reposicion por desnaturalizacion de contrato modal"},
    {"id": "M2", "nivel": "media", "desc": "Horas extras y comisiones",
     "query": "procedencia del pago de horas extras y comisiones"},
    {"id": "M3", "nivel": "media", "desc": "No confiscatoriedad tributos",
     "query": "aplicacion del principio de no confiscatoriedad en tributos"},
    # Complejas (top_k esperado: 10-15)
    {"id": "C1", "nivel": "compleja", "desc": "Reposición contrato específico",
     "query": "cuales son los requisitos para que proceda la reposicion de un trabajador contratado por servicio especifico cuando la empresa extingue el vinculo antes de concluir la obra contratada"},
    {"id": "C2", "nivel": "compleja", "desc": "Diferencia nulidades CS",
     "query": "diferencia entre la nulidad de cosa juzgada fraudulenta y la nulidad de oficio segun la jurisprudencia de la corte suprema"},
    # Estadísticas (top_k esperado: 10-15, graph_depth=2)
    {"id": "E1", "nivel": "estadistica", "desc": "Jueces con más casos",
     "query": "que juez de la corte suprema ha emitido mas sentencias sobre despido arbitrario"},
    {"id": "E2", "nivel": "estadistica", "desc": "Leyes más citadas laboral",
     "query": "cuales son las leyes mas citadas en los procesos laborales sobre reposicion"},
    # Hipotética
    {"id": "H1", "nivel": "compleja", "desc": "Despido verbal sin preaviso",
     "query": "un trabajador fue despedido verbalmente sin carta de preaviso ni comunicacion escrita, que acciones legales proceden segun la jurisprudencia peruana"},
]

def escape_shell_query(q):
    return q.replace('"', '\\"').replace("'", "\\'")

def run_query(q_item):
    q = q_item["query"]
    safe_q = escape_shell_query(q)
    cmd = f'cd {PROJECT_DIR} && {PYTHON_EXE} graphrag_pro.py --query "{safe_q}"'

    start = time.time()
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                                timeout=180, encoding='utf-8', errors='replace')
        elapsed = time.time() - start
        return {"success": True, "output": result.stdout + result.stderr, "elapsed": elapsed}
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "[TIMEOUT]", "elapsed": 180}
    except Exception as e:
        return {"success": False, "output": f"[ERROR] {e}", "elapsed": time.time() - start}

def find_latest_audit():
    files = sorted(glob.glob(os.path.join(PROJECT_DIR, "consultas_guardadas", "*_audit.json")),
                   key=os.path.getmtime)
    if files:
        with open(files[-1], 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

def get_critic_text(verdict):
    if not verdict:
        return "N/A"
    parts = []
    if verdict.get("verified"):
        parts.append(f"V:{verdict['verified']}")
    if verdict.get("hallucinated"):
        parts.append(f"H:{verdict['hallucinated']}")
    if verdict.get("unverifiable"):
        parts.append(f"U:{verdict['unverifiable']}")
    score = verdict.get("score", 0)
    return " ".join(parts) + f" score={score:.0%}" if parts else f"score={score:.0%}"

def get_strategy_text(strategy):
    if not strategy:
        return "fallback"
    top_k = strategy.get("top_k", 7)
    mode = strategy.get("retrieval_mode", "hybrid")
    graph = "S"+str(strategy.get("graph_depth",1)) if strategy.get("use_graph") else "N"
    return f"{strategy.get('complexity','?')} k={top_k} m={mode} g={graph}"

# ═══ MAIN ═══
print("=" * 80)
print("BATERÍA RETRIEVAL STRATEGIST + CRITIC - 10 CONSULTAS")
print("=" * 80)

results = []
for i, q_item in enumerate(QUERIES):
    print(f"\n[{i+1}/10] {q_item['id']} ({q_item['nivel']}) - {q_item['desc']}")
    sys.stdout.flush()

    result = run_query(q_item)
    result.update(q_item)

    # Buscar audit generado
    result["audit"] = find_latest_audit()
    if result["audit"]:
        strategy = result["audit"].get("retrieval", {}).get("hybrid", {}).get("strategy", {})
        critic = result["audit"].get("critic", {})
        result["strategy_text"] = get_strategy_text(strategy)
        result["critic_text"] = get_critic_text(critic)
    else:
        result["strategy_text"] = "N/A"
        result["critic_text"] = "N/A"

    status = "✅" if result["success"] else "❌"
    print(f"  {status} {result['elapsed']:.1f}s | {result['strategy_text']} | Critic: {result['critic_text']}")
    sys.stdout.flush()
    results.append(result)

# ═══ REPORTE ═══
lines = []
lines.append("=" * 80)
lines.append(f"BATERÍA RETRIEVAL STRATEGIST + CRITIC")
lines.append(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
lines.append(f"Total consultas: {len(results)}")
lines.append(f"Exitosas: {sum(1 for r in results if r['success'])}")
lines.append(f"Tiempo total: {sum(r['elapsed'] for r in results):.1f}s")
lines.append(f"Promedio: {sum(r['elapsed'] for r in results)/len(results):.1f}s")
lines.append("")

# Tabla resumen
lines.append("-" * 100)
lines.append(f"{'ID':<5} {'Nivel':<12} {'T(s)':<7} {'Estrategia':<35} {'Critic':<25} {'Desc':<20}")
lines.append("-" * 100)
for r in results:
    lines.append(f"{r['id']:<5} {r['nivel']:<12} {r['elapsed']:<7.1f} "
                 f"{r['strategy_text']:<35} {r['critic_text']:<25} {r['desc'][:20]}")
lines.append("")

# Detalle
lines.append("=" * 80)
lines.append("DETALLE POR CONSULTA")
lines.append("=" * 80)
lines.append("")

for r in results:
    lines.append("#" * 80)
    lines.append(f"## {r['id']} | Nivel: {r['nivel']}")
    lines.append(f"**Query:** {r['query'][:100]}")
    lines.append(f"**Tiempo:** {r['elapsed']:.1f}s")
    lines.append(f"**Estado:** {'✅ Éxito' if r['success'] else '❌ Falló'}")

    audit = r.get("audit")
    if audit:
        hybrid = audit.get("retrieval", {}).get("hybrid", {})
        strategy = hybrid.get("strategy", {})
        lines.append(f"")
        lines.append(f"--- ESTRATEGIA DE RECUPERACIÓN ---")
        if strategy:
            lines.append(f"Complejidad: {strategy.get('complexity','?')}")
            lines.append(f"top_k: {strategy.get('top_k',7)} docs | mode: {strategy.get('retrieval_mode','hybrid')}")
            lines.append(f"Gráfo: {'S'+str(strategy.get('graph_depth',1)) if strategy.get('use_graph') else 'N'}")
            lines.append(f"Razonamiento: {strategy.get('reasoning','')[:120]}...")
        else:
            lines.append("(estrategia por defecto)")

        lines.append(f"")
        lines.append(f"--- RETRIEVAL ---")
        lines.append(f"top_k={hybrid.get('top_k',7)} | fusion: {hybrid.get('fusion_params',{})}")
        faiss_n = len(hybrid.get('faiss_raw', []))
        bm25_n = len(hybrid.get('bm25_raw', []))
        rrf_n = len(hybrid.get('rrf_ranked', []))
        filtered_n = len(hybrid.get('chunks_filtered_out', []))
        lines.append(f"FAISS: {faiss_n} chunks | BM25: {bm25_n} | RRF top: {rrf_n} | Descartados: {filtered_n}")

        critic = audit.get("critic", {})
        lines.append(f"")
        lines.append(f"--- CRÍTICO DE CITAS ---")
        lines.append(f"Score: {critic.get('score',0):.0%} | Pasó: {critic.get('passed','?')}")
        lines.append(f"Verificadas: {critic.get('verified',0)} | Sospechosas: {critic.get('hallucinated',0)} | No verificables: {critic.get('unverifiable',0)}")
        if critic.get('errors'):
            for e in critic['errors']:
                lines.append(f"  ⚠️ {e}")
        if critic.get('warnings'):
            for w in critic['warnings']:
                lines.append(f"  💡 {w}")
    else:
        lines.append("[Sin auditoría]")
    lines.append("")

lines.append("=" * 80)
lines.append("FIN DEL REPORTE")
lines.append("=" * 80)

os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
with open(REPORT_PATH, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

# Also save fixed name
fixed_path = os.path.join(PROJECT_DIR, "data/bateria_10_strategist_critic.txt")
with open(fixed_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(f"\n✅ Reporte guardado en:")
print(f"   {REPORT_PATH}")
print(f"   {fixed_path}")
