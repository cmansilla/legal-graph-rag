"""
BATERÍA FINAL COMPLETA — 20 CONSULTAS NUEVAS
=============================================
20 consultas inéditas (distintas a baterías anteriores).
Niveles variados: simple, media, compleja, estadística.
Mide: estrategia, critic, feedback loop, tiempos, auditoría.

Ejecuta el pipeline completo: Strategist → Hybrid Search →
Graph Analyst → Synthesis → Critic → Feedback Loop
"""
import os, sys, json, re, time, subprocess, glob
from datetime import datetime

PROJECT_DIR = "/mnt/d/PyCode/ResumenTokensJurisprudencias"
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
REPORT_PATH = os.path.join(PROJECT_DIR, f"data/bateria_final_completa_{TIMESTAMP}.txt")
FIXED_PATH = os.path.join(PROJECT_DIR, "data/bateria_final_completa.txt")

# 20 consultas NUEVAS (ninguna repetida de baterías anteriores)
QUERIES = [
    # ── NIVEL 1: Simple (< 7 palabras, 1 concepto) ──
    {"id":"S01","nivel":"simple","area":"Laboral","desc":"Estabilidad laboral",
     "query":"estabilidad laboral de entrada"},
    {"id":"S02","nivel":"simple","area":"Penal","desc":"Legítima defensa",
     "query":"requisitos de la legitima defensa"},
    {"id":"S03","nivel":"simple","area":"Civil","desc":"Prescripción adquisitiva",
     "query":"prescripcion adquisitiva de dominio"},
    {"id":"S04","nivel":"simple","area":"Tributario","desc":"Base imponible",
     "query":"base imponible del impuesto predial"},
    {"id":"S05","nivel":"simple","area":"Constitucional","desc":"Debido proceso",
     "query":"derecho al debido proceso"},

    # ── NIVEL 2: Media (7-14 palabras, 2 conceptos) ──
    {"id":"M01","nivel":"media","area":"Laboral","desc":"Despido y embarazo",
     "query":"despido durante el periodo de prueba y proteccion de la maternidad"},
    {"id":"M02","nivel":"media","area":"Civil","desc":"Arras confirmatorias y penal",
     "query":"diferencia entre arras confirmatorias y arras penales"},
    {"id":"M03","nivel":"media","area":"Penal","desc":"Tenencia y porte de armas",
     "query":"tenencia ilegal de armas y porte indebido de arma de fuego"},
    {"id":"M04","nivel":"media","area":"Familia","desc":"Alimentos y tenencia",
     "query":"criterios para fijar alimentos y tenencia compartida"},
    {"id":"M05","nivel":"media","area":"Procesal","desc":"Prueba de oficio y carga",
     "query":"procedencia de la prueba de oficio y carga de la prueba"},

    # ── NIVEL 3: Compleja (>= 15 palabras, multi-arista o comparativa) ──
    {"id":"C01","nivel":"compleja","area":"Laboral-Colectivo","desc":"Negociación colectiva y huelga",
     "query":"cuales son los requisitos para declarar la ilegalidad de una huelga y cual es el procedimiento sancionador contra los trabajadores que participan en ella"},
    {"id":"C02","nivel":"compleja","area":"Constitucional","desc":"Control difuso y concentrado",
     "query":"diferencia entre el control difuso de constitucionalidad y el control concentrado segun la jurisprudencia del tribunal constitucional peruano"},
    {"id":"C03","nivel":"compleja","area":"Penal-Económico","desc":"Lavado de activos y delito precedente",
     "query":"que requisitos debe cumplir el delito precedente para configurar el lavado de activos y como se diferencia del delito de receptacion"},
    {"id":"C04","nivel":"compleja","area":"Procesal-Civil","desc":"Tercería y medidas cautelares",
     "query":"en que casos procede la terceria de dominio frente a un embargo y cual es el tratamiento jurisprudencial de las medidas cautelares fuera del proceso"},
    {"id":"C05","nivel":"compleja","area":"Ambiental","desc":"Daño ambiental y responsabilidad",
     "query":"cual es el regimen de responsabilidad civil por daño ambiental y como se aplica el principio contaminador pagador en la jurisprudencia peruana"},

    # ── NIVEL 4: Estadística / Cuantitativa ──
    {"id":"E01","nivel":"estadistica","area":"Estadístico","desc":"Demandado más frecuente",
     "query":"que empresa privada es la mas demandada en procesos laborales"},
    {"id":"E02","nivel":"estadistica","area":"Estadístico","desc":"Materia más litigada",
     "query":"cual es la materia mas litigada en la corte suprema"},
    {"id":"E03","nivel":"estadistica","area":"Estadístico","desc":"Sala con más carga",
     "query":"que sala de la corte suprema tiene mas casos registrados"},
    {"id":"E04","nivel":"estadistica","area":"Comparativo","desc":"Indemnización vs reposición",
     "query":"comparar la frecuencia de sentencias que ordenan indemnizacion frente a las que ordenan reposicion en casos de despido arbitrario"},
    {"id":"E05","nivel":"compleja","area":"Hipotético","desc":"Accidente de trabajo y responsabilidad",
     "query":"un trabajador sufrio un accidente laboral porque el empleador no implemento las medidas de seguridad obligatorias que acciones legales tiene el trabajador y que indemnizaciones puede reclamar segun la jurisprudencia"},
]


def run_query(q_item):
    q = q_item["query"]
    safe_q = q.replace('"', '\\"').replace("'", "\\'")
    cmd = f'cd {PROJECT_DIR} && python3 graphrag_pro.py --query "{safe_q}"'
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
        try:
            with open(files[-1], 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return None


def extract_critic_header(output):
    """Extrae las líneas del crítico del output."""
    lines = []
    capture = False
    for line in output.split("\n"):
        if "CRÍTICO DE CITAS" in line:
            capture = True
        if capture:
            lines.append(line.strip())
            if "score:" in line and ("%" in line or "100" in line):
                capture = False
                break
    return "\n".join(lines[:8])


def extract_feedback(output):
    """Busca si hubo feedback loop."""
    if "Corrigiendo citas" in output:
        return "SÍ"
    return "no"


# ═══ MAIN ═══
print("=" * 80)
print("BATERÍA FINAL COMPLETA — 20 CONSULTAS NUEVAS")
print("=" * 80)
print()

results = []
for i, q_item in enumerate(QUERIES):
    print(f"[{i+1:>2}/20] {q_item['id']} ({q_item['nivel']:<12}) {q_item['desc']:<35} ", end="", flush=True)
    result = run_query(q_item)
    result.update(q_item)
    result["audit"] = find_latest_audit()

    status = "✅" if result["success"] else "❌"
    
    if result["audit"]:
        h = result["audit"].get("retrieval", {}).get("hybrid", {})
        strat = h.get("strategy", {})
        result["strategy_s"] = f"{strat.get('complexity','?')} k={strat.get('top_k','?')} g={'S'+str(strat.get('graph_depth',1)) if strat.get('use_graph') else 'N'}"
        result["faiss_n"] = len(h.get("faiss_raw", []))
        result["bm25_n"] = len(h.get("bm25_raw", []))
        result["rrf_n"] = len(h.get("rrf_ranked", []))
        result["filtered_n"] = len(h.get("chunks_filtered_out", []))
        
        crit = result["audit"].get("critic", {})
        result["critic_score"] = crit.get("score", 0)
        result["critic_hallu"] = crit.get("hallucinated", 0)
        result["critic_verified"] = crit.get("verified", 0)
        
        fb = result["audit"].get("feedback", {})
        result["feedback_iter"] = fb.get("iterations", 0)
    else:
        result["strategy_s"] = "N/A"
        result["critic_score"] = 0
        result["feedback_iter"] = 0
    
    fb_mark = "🔄" if result.get("feedback_iter", 0) > 0 else ""
    print(f"{status} {result['elapsed']:5.1f}s | {result['strategy_s']:<20} | critic:{result.get('critic_score',0):.0%} {fb_mark}")
    sys.stdout.flush()
    results.append(result)

# ═══ GENERAR REPORTE ═══
lines = []
def L(s): lines.append(s)

L("=" * 110)
L("BATERÍA FINAL COMPLETA — 20 CONSULTAS NUEVAS — TRazabilidad TOTAL")
L(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
L(f"Total: {len(results)} | Exitosas: {sum(1 for r in results if r['success'])}")
L(f"Tiempo total: {sum(r['elapsed'] for r in results):.1f}s | Promedio: {sum(r['elapsed'] for r in results)/len(results):.1f}s")
L(f"Feedback loop activado: {sum(1 for r in results if r.get('feedback_iter',0) > 0)} consultas")
L("")

# Tabla resumen
L("-" * 110)
hdr = f"{'ID':<5} {'Nivel':<12} {'T(s)':<6} {'Estrategia':<22} {'F':<4} {'BM':<4} {'RRF':<5} {'Fil':<4} {'CV':<4} {'CH':<4} {'Score':<6} {'FB':<4} {'Desc':<20}"
L(hdr)
L("-" * 110)
for r in results:
    fb = "🔄" if r.get("feedback_iter", 0) > 0 else "—"
    L(f"{r['id']:<5} {r['nivel']:<12} {r['elapsed']:<6.1f} {r['strategy_s']:<22} "
      f"{r.get('faiss_n',0):<4} {r.get('bm25_n',0):<4} {r.get('rrf_n',0):<5} {r.get('filtered_n',0):<4} "
      f"{r.get('critic_verified',0):<4} {r.get('critic_hallu',0):<4} {r.get('critic_score',0):<6.0%} "
      f"{fb:<4} {r['desc'][:20]}")
L("")

# Precisión por nivel
L("=" * 110)
L("PRECISIÓN DE CLASIFICACIÓN (STRATEGIST)")
L("=" * 110)
L("")
from collections import Counter
by_level = {}
for r in results:
    lvl = r["nivel"]
    by_level.setdefault(lvl, {"total": 0})
    by_level[lvl]["total"] += 1
    strat_lvl = r["strategy_s"].split()[0] if r["strategy_s"] else "?"
    by_level[lvl][strat_lvl] = by_level[lvl].get(strat_lvl, 0) + 1

for lvl in ["simple", "media", "compleja", "estadistica"]:
    if lvl in by_level:
        d = by_level[lvl]
        correct = d.get(lvl, 0)
        total = d["total"]
        pct = correct / total * 100 if total else 0
        bar = "█" * int(pct // 5) + "░" * (20 - int(pct // 5))
        L(f"  {lvl:<12} {correct}/{total} ({pct:.0f}%) {bar}")

# Distribución de estrategias
L("")
L("ESTRATEGIAS APLICADAS:")
estrats = Counter()
for r in results:
    estrats[r["strategy_s"]] += 1
for s, n in estrats.most_common():
    L(f"  {s:<25} {n:>2} consultas")

# Estadísticas del crítico
L("")
L("ESTADÍSTICAS DEL CRÍTICO:")
critic_100 = sum(1 for r in results if r.get("critic_score", 0) >= 1.0)
critic_ok = sum(1 for r in results if r.get("critic_score", 0) >= 0.5)
hallu_total = sum(r.get("critic_hallu", 0) for r in results)
L(f"  Score 100%:    {critic_100}/{len(results)}")
L(f"  Score >= 50%:  {critic_ok}/{len(results)}")
L(f"  Total halluc:  {hallu_total}")
L(f"  Feedback loop: {sum(1 for r in results if r.get('feedback_iter',0) > 0)}/{len(results)}")

# Detalle por consulta
L("")
L("=" * 110)
L("DETALLE POR CONSULTA")
L("=" * 110)
L("")

for r in results:
    L("#" * 110)
    L(f"## {r['id']} | {r['nivel'].upper()} | {r['area']}")
    L(f"**Desc:** {r['desc']}")
    L(f"**Query:** {r['query'][:130]}")
    L(f"**Tiempo:** {r['elapsed']:.1f}s | **Estado:** {'✅' if r['success'] else '❌'}")
    
    audit = r.get("audit")
    if audit:
        meta = audit.get("metadata", {})
        L(f"**Router:** {meta.get('decision','?')} | **HyDE:** {meta.get('hyde_query','')[:100]}...")
        
        h = audit.get("retrieval", {}).get("hybrid", {})
        strat = h.get("strategy", {})
        L("")
        L("  → ESTRATEGIA")
        L(f"    {strat.get('complexity','?')} | top_k={strat.get('top_k','?')} | mode={strat.get('retrieval_mode','?')}")
        L(f"    Grafo: {'S'+str(strat.get('graph_depth','?')) if strat.get('use_graph') else 'N'}")
        L(f"    Razón: {strat.get('reasoning','')[:120]}")
        
        L("")
        L("  → RETRIEVAL")
        L(f"    FAISS: {len(h.get('faiss_raw',[]))} | BM25: {len(h.get('bm25_raw',[]))} | "
          f"RRF: {len(h.get('rrf_ranked',[]))} | Filtrados: {len(h.get('chunks_filtered_out',[]))}")
        
        g = audit.get("retrieval", {}).get("graph", {})
        L("")
        L("  → GRAPH ANALYST")
        L(f"    Jueces top: {json.dumps(g.get('top_jueces',[])[:3], ensure_ascii=False)}")
        L(f"    Leyes top: {json.dumps(g.get('top_leyes',[])[:3], ensure_ascii=False)}")
        L(f"    Cadenas: {g.get('chains_encontradas',0)}")
        
        crit = audit.get("critic", {})
        fb = audit.get("feedback", {})
        L("")
        L("  → CRÍTICO + FEEDBACK")
        L(f"    Score: {crit.get('score',0):.0%} | Pasó: {crit.get('passed','?')}")
        L(f"    Verificadas: {crit.get('verified',0)} | Sospechosas: {crit.get('hallucinated',0)}")
        L(f"    Feedback loop: {fb.get('iterations',0)} iteraciones")
        if crit.get('errors'):
            for e in crit['errors']:
                L(f"    ⚠️ {e}")
    else:
        L("  [Sin auditoría]")
    L("")

L("=" * 110)
L("FIN DEL REPORTE")
L(f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
L("=" * 110)

# Guardar
report_text = "\n".join(lines)
os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
with open(REPORT_PATH, "w", encoding="utf-8") as f:
    f.write(report_text)
with open(FIXED_PATH, "w", encoding="utf-8") as f:
    f.write(report_text)

print(f"\n✅ Reporte guardado:")
print(f"   {REPORT_PATH}")
print(f"   {FIXED_PATH}")
print(f"\n📊 {sum(1 for r in results if r['success'])}/20 exitosas · "
      f"{sum(r['elapsed'] for r in results):.1f}s total · "
      f"Critic 100%: {critic_100}/{len(results)} · "
      f"Feedback: {sum(1 for r in results if r.get('feedback_iter',0) > 0)}")
