"""
BATERÍA FINAL DE 20 CONSULTAS — Strategist Híbrido + Critic + Auditoría
=======================================================================
Ejecuta 20 consultas de distintos niveles contra graphrag_pro.py,
captura estrategia, crítico, auditoría granular, y genera reporte TXT.
"""
import os, sys, json, re, time, subprocess, glob
from datetime import datetime

PROJECT_DIR = "/mnt/d/PyCode/ResumenTokensJurisprudencias"
PYTHON_EXE = "python3"
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
REPORT_PATH = os.path.join(PROJECT_DIR, f"data/bateria_final_20_{TIMESTAMP}.txt")
FIXED_PATH = os.path.join(PROJECT_DIR, "data/bateria_final_20_consolidado.txt")

QUERIES = [
    # NIVEL 1: Simple (< 8 palabras, 1 concepto)
    {"id":"S01","nivel":"simple","materia":"Laboral","desc":"Despido arbitrario",
     "query":"despido arbitrario"},
    {"id":"S02","nivel":"simple","materia":"Civil","desc":"Nulidad cosa juzgada",
     "query":"nulidad de cosa juzgada fraudulenta"},
    {"id":"S03","nivel":"simple","materia":"Familia","desc":"Violencia familiar",
     "query":"medidas de proteccion en violencia familiar"},
    {"id":"S04","nivel":"simple","materia":"Tributario","desc":"Gastos deducibles",
     "query":"gastos deducibles impuesto a la renta"},
    {"id":"S05","nivel":"simple","materia":"Constitucional","desc":"Hábeas data",
     "query":"procedencia del habeas data"},

    # NIVEL 2: Media (8-14 palabras, 2 conceptos)
    {"id":"M01","nivel":"media","materia":"Laboral","desc":"Reposición + desnaturalización",
     "query":"reposicion por desnaturalizacion de contrato modal"},
    {"id":"M02","nivel":"media","materia":"Laboral","desc":"Horas extras + comisiones",
     "query":"procedencia del pago de horas extras y comisiones"},
    {"id":"M03","nivel":"media","materia":"Constitucional-Tributario","desc":"No confiscatoriedad",
     "query":"aplicacion del principio de no confiscatoriedad en tributos"},
    {"id":"M04","nivel":"media","materia":"Civil-Procesal","desc":"Caducidad procesos civiles",
     "query":"excepcion de caducidad en procesos civiles"},
    {"id":"M05","nivel":"media","materia":"Penal","desc":"Prescripción acción penal",
     "query":"prescripcion de la accion penal en delitos"},

    # NIVEL 3: Compleja (>= 15 palabras, multi-arista)
    {"id":"C01","nivel":"compleja","materia":"Laboral","desc":"Reposición contrato específico",
     "query":"cuales son los requisitos para que proceda la reposicion de un trabajador contratado por servicio especifico cuando la empresa extingue el vinculo antes de concluir la obra contratada"},
    {"id":"C02","nivel":"compleja","materia":"Constitucional-Laboral","desc":"TC + reposición",
     "query":"que criterios ha establecido el tribunal constitucional sobre el derecho al trabajo y la reposicion en casos de contratos modales desnaturalizados"},
    {"id":"C03","nivel":"compleja","materia":"Civil-Procesal","desc":"Nulidad fraude vs oficio",
     "query":"diferencia entre la nulidad de cosa juzgada fraudulenta y la nulidad de oficio segun la jurisprudencia de la corte suprema"},
    {"id":"C04","nivel":"compleja","materia":"Laboral-Procesal","desc":"Casación infracción normativa",
     "query":"procedencia del recurso de casacion por infraccion normativa en procesos laborales sobre pago de beneficios sociales"},
    {"id":"C05","nivel":"compleja","materia":"Tributario","desc":"TF + capacidad contributiva",
     "query":"cual es la tendencia jurisprudencial del tribunal fiscal respecto a la aplicacion del principio de capacidad contributiva en el impuesto a la renta de tercera categoria"},

    # NIVEL 4: Estadística / Comparativa
    {"id":"E01","nivel":"estadistica","materia":"Estadístico","desc":"Juez más sentencias",
     "query":"que juez de la corte suprema ha emitido mas sentencias sobre despido arbitrario"},
    {"id":"E02","nivel":"estadistica","materia":"Estadístico","desc":"Leyes más citadas",
     "query":"cuales son las leyes mas citadas en los procesos laborales sobre reposicion"},
    {"id":"E03","nivel":"estadistica","materia":"Estadístico","desc":"Entidad más demandada",
     "query":"que entidad del estado es la mas demandada en procesos de habeas data"},
    {"id":"E04","nivel":"compleja","materia":"Comparativo","desc":"TC vs Corte Suprema",
     "query":"comparar el tratamiento del despido arbitrario entre el tribunal constitucional y la corte suprema"},
    {"id":"E05","nivel":"compleja","materia":"Hipotético","desc":"Despido verbal sin preaviso",
     "query":"un trabajador fue despedido verbalmente sin carta de preaviso ni comunicacion escrita que acciones legales proceden segun la jurisprudencia peruana"},
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
        try:
            with open(files[-1], 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return None

# ═══ MAIN ═══
print("=" * 80)
print("BATERÍA FINAL — STRATEGIST HÍBRIDO + CRITIC — 20 CONSULTAS")
print("=" * 80)
print()

results = []
for i, q_item in enumerate(QUERIES):
    print(f"[{i+1:>2}/20] {q_item['id']} ({q_item['nivel']:<12}) {q_item['desc']:<35} ", end="", flush=True)
    result = run_query(q_item)
    result.update(q_item)
    result["audit"] = find_latest_audit()
    
    # Extraer métricas
    status = "✅" if result["success"] else "❌"
    if result["audit"]:
        h = result["audit"].get("retrieval", {}).get("hybrid", {})
        strat = h.get("strategy", {})
        result["strategy"] = f"{strat.get('complexity','?')} k={strat.get('top_k','?')} g={'S'+str(strat.get('graph_depth',1)) if strat.get('use_graph') else 'N'}"
        result["fusion"] = h.get("fusion_params", {})
        result["faiss_n"] = len(h.get("faiss_raw", []))
        result["bm25_n"] = len(h.get("bm25_raw", []))
        result["rrf_n"] = len(h.get("rrf_ranked", []))
        result["filtered_n"] = len(h.get("chunks_filtered_out", []))
        
        crit = result["audit"].get("critic", {})
        result["critic_score"] = crit.get("score", 0)
        result["critic_hallu"] = crit.get("hallucinated", 0)
        result["critic_verified"] = crit.get("verified", 0)
        result["critic_unver"] = crit.get("unverifiable", 0)
        result["critic_passed"] = crit.get("passed", True)
    else:
        result["strategy"] = "N/A"
        result["critic_score"] = 0
    
    print(f"{status} {result['elapsed']:5.1f}s | {result['strategy']:<20} | critic:{result.get('critic_score',0):.0%}")
    sys.stdout.flush()
    results.append(result)

# ═══ GENERAR REPORTE ═══
lines = []
def L(s): lines.append(s)

L("=" * 100)
L("BATERÍA FINAL — 20 CONSULTAS — STRATEGIST HÍBRIDO + CRITIC + AUDITORÍA")
L(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
L(f"Total: {len(results)} | Exitosas: {sum(1 for r in results if r['success'])}")
L(f"Tiempo total: {sum(r['elapsed'] for r in results):.1f}s | Promedio: {sum(r['elapsed'] for r in results)/len(results):.1f}s")
L("")

# Tabla resumen
L("-" * 120)
hdr = f"{'ID':<5} {'Nivel':<12} {'T(s)':<6} {'Estrategia':<22} {'FAISS':<7} {'BM25':<7} {'RRF':<5} {'Fil':<4} {'CriticV':<4} {'CriticH':<4} {'Score':<6} {'Desc':<20}"
L(hdr)
L("-" * 120)
for r in results:
    cv = r.get("critic_verified", 0)
    ch = r.get("critic_hallu", 0)
    sc = r.get("critic_score", 0)
    L(f"{r['id']:<5} {r['nivel']:<12} {r['elapsed']:<6.1f} {r['strategy']:<22} "
      f"{r.get('faiss_n',0):<7} {r.get('bm25_n',0):<7} {r.get('rrf_n',0):<5} {r.get('filtered_n',0):<4} "
      f"{cv:<4} {ch:<4} {sc:<6.0%} {r['desc'][:20]}")
L("")

# Tabla de estrategias
L("=" * 100)
L("ESTRATEGIAS APLICADAS")
L("=" * 100)
L("")
estrats = {}
for r in results:
    s = r.get("strategy", "N/A")
    estrats[s] = estrats.get(s, 0) + 1
for s, n in sorted(estrats.items(), key=lambda x: -x[1]):
    L(f"  {s:<25} {n:>2} consultas")

# Resumen de aciertos por nivel
L("")
L("=" * 100)
L("PRECISIÓN DE CLASIFICACIÓN")
L("=" * 100)
L("")
by_level = {}
for r in results:
    lvl = r["nivel"]
    by_level.setdefault(lvl, {"total": 0})
    by_level[lvl]["total"] += 1
    # Extraer clasificación del strategist
    strat_str = r.get("strategy", "")
    strat_lvl = strat_str.split()[0] if strat_str else "?"
    by_level[lvl][strat_lvl] = by_level[lvl].get(strat_lvl, 0) + 1

for lvl in ["simple", "media", "compleja", "estadistica"]:
    if lvl in by_level:
        d = by_level[lvl]
        correct = d.get(lvl, 0)
        total = d["total"]
        pct = correct / total * 100 if total else 0
        bar = "█" * int(pct // 5) + "░" * (20 - int(pct // 5))
        L(f"  {lvl:<12} {correct}/{total} ({pct:.0f}%) {bar}")

# Detalle por consulta
L("")
L("=" * 100)
L("DETALLE POR CONSULTA")
L("=" * 100)
L("")

for r in results:
    L("#" * 100)
    L(f"## {r['id']} | {r['nivel'].upper()} | {r['materia']}")
    L(f"**Desc:** {r['desc']}")
    L(f"**Query:** {r['query'][:120]}")
    L(f"**Tiempo:** {r['elapsed']:.1f}s | **Estado:** {'✅' if r['success'] else '❌'}")
    
    audit = r.get("audit")
    if audit:
        meta = audit.get("metadata", {})
        L(f"**Router:** {meta.get('decision','?')} | **HyDE:** {meta.get('hyde_query','?')[:80]}...")
        
        h = audit.get("retrieval", {}).get("hybrid", {})
        strat = h.get("strategy", {})
        L("")
        L("  → ESTRATEGIA")
        L(f"    Complejidad: {strat.get('complexity','?')} | top_k={strat.get('top_k','?')} | mode={strat.get('retrieval_mode','?')}")
        L(f"    Gráfo: {'S'+str(strat.get('graph_depth','?')) if strat.get('use_graph') else 'N'}")
        L(f"    Razón: {strat.get('reasoning','')[:120]}")
        
        L("")
        L("  → RETRIEVAL")
        L(f"    FAISS: {len(h.get('faiss_raw',[]))} chunks | BM25: {len(h.get('bm25_raw',[]))} | "
          f"RRF: {len(h.get('rrf_ranked',[]))} | Filtrados: {len(h.get('chunks_filtered_out',[]))}")
        L(f"    Fusion: {h.get('fusion_params',{})}")
        if h.get("rrf_ranked"):
            L(f"    Top-3 chunks RRF:")
            for c in h["rrf_ranked"][:3]:
                L(f"      #{c['rank']} doc={c['doc_id']} rrf={c['rrf_score']:.4f} {c.get('snippet','')[:100]}...")
        
        crit = audit.get("critic", {})
        L("")
        L("  → CRÍTICO DE CITAS")
        L(f"    Score: {crit.get('score',0):.0%} | Pasó: {crit.get('passed','?')}")
        L(f"    Verificadas: {crit.get('verified',0)} | Sospechosas: {crit.get('hallucinated',0)} | No verificables: {crit.get('unverifiable',0)}")
        if crit.get('errors'):
            for e in crit['errors']:
                L(f"    ⚠️ {e}")
        
        g = audit.get("retrieval", {}).get("graph", {})
        L("")
        L("  → GRAFO")
        L(f"    Nodos: {len(g.get('nodes_with_data',[]))} | Vecinos: {len(g.get('neighbors_found',[]))} | Aristas: {g.get('total_edges_processed',0)}")
    else:
        L("  [Sin auditoría]")
    L("")

L("=" * 100)
L("FIN DEL REPORTE")
L(f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
L("=" * 100)

# Guardar
report_text = "\n".join(lines)
os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
with open(REPORT_PATH, "w", encoding="utf-8") as f:
    f.write(report_text)
with open(FIXED_PATH, "w", encoding="utf-8") as f:
    f.write(report_text)

print(f"\n✅ Reportes guardados:")
print(f"   {REPORT_PATH}")
print(f"   {FIXED_PATH}")
print(f"\n📊 Resumen: {sum(1 for r in results if r['success'])}/20 exitosas, "
      f"{sum(r['elapsed'] for r in results):.1f}s total")
