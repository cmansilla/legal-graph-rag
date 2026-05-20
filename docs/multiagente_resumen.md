# Lex RAG → Multi-Agente: Análisis completo

## 1. ¿Qué cambia?

### Hoy: Pipeline secuencial (1 agente genérico)
```
Usuario → Router → Retrieval → Synthesizer → Respuesta
           (1 call)  (0 calls)   (1-2 calls) 
```
Total: **2-3 LLM calls** · Sin verificación · top_k fijo · Sin feedback

### Multi-Agente: Pipeline orquestado con especialistas
```
Usuario → Orchestrator → Router + Strategist + GraphAnalyst → Retrieval Tools
                                              ↓
                                    Legal Writer → Critic → (loop?) → Respuesta
```
Total: **5-8 LLM calls** · Verificación de citas · top_k dinámico · Feedback loop

---

## 2. Los 6 agentes propuestos

| Agente | Rol | LLM calls | Herramientas |
|--------|-----|-----------|--------------|
| 🔀 Router | Clasifica consulta + HyDE | 1 | Prompt |
| 🎯 Retrieval Strategist | Decide top_k, pesos, fuentes | 1 | Prompt + metadatos |
| 🕸️ Graph Analyst | Analiza NetworkX (patrones, frecuencias) | 0-1 | NetworkX API + LLM |
| ✍️ Legal Writer | Redacta dictamen con citas | 1 | Prompt + contexto |
| 🔍 Critic | Verifica citas, detecta alucinaciones | 1-2 | Prompt + FAISS lookup |
| 🧠 Orchestrator | Coordina flujo, decide iteraciones | 0-1 | Delegate + control |

---

## 3. Costos

| Métrica | Actual | Multi-Agente |
|---------|--------|-------------|
| LLM calls/query | 2-3 | 5-8 |
| Input tokens/query | ~4,500 | ~12,000 |
| Output tokens/query | ~1,200 | ~3,500 |
| Latencia | ~12-18s | ~15-28s |
| Costo/query (DeepSeek) | ~$0.002-0.015 | ~$0.008-0.06 |
| Costo mensual (3K queries) | ~$6 | ~$24 |

**Mitigación**: Agentes auxiliares (router, strategist, critic) pueden usar modelos
pequeños (8B) que cuestan 10× menos. Con Grog (gratuito) el incremento es solo
en latencia, no en dinero.

---

## 4. Impacto en calidad

### ✅ Mejoras
- **Menos alucinaciones** — Critic verifica citas contra FAISS/metadata
- **Recuperación adaptativa** — top_k dinámico según complejidad
- **Estadísticas precisas** — Graph Analyst cuenta con NetworkX, no "adivina"
- **Estructura consistente** — Writer especializado en formato forense
- **Trazabilidad multi-nivel** — audit de cada decisión de cada agente

### ⚠️ Riesgos
- **Latencia +50%** (~15-28s)
- **Complejidad de debugging** — 6× más puntos de fallo
- **Overhead de tokens** — contexto repetido entre agentes
- **Loops infinitos** — Critic podría rechazar iterativamente (necesita límite)
- **Código 3-4× más grande**

---

## 5. Plan por fases (recomendación)

| Fase | Qué | Esfuerzo | Riesgo | Valor |
|------|-----|----------|--------|-------|
| **1** | Critic Agent (verificador de citas) | 1-2 días | 🟢 Bajo | 🔥 Alto |
| **2** | Retrieval Strategist (top_k dinámico) | 2-3 días | 🟡 Medio | 🔥 Alto |
| **3** | Graph Analyst (estadísticas precisas) | 2-3 días | 🟡 Medio | 🔥 Alto |
| **4** | Feedback loop (critic → re-write) | 3-5 días | 🔴 Alto | 💎 Máximo |
| **5** | Orchestrator formal | 3-5 días | 🔴 Alto | 💎 Máximo |

---

## 6. Veredicto

**Implementa solo el Critic Agent (Fase 1) ahora.** Bajo riesgo, 1-2 días,
resuelve el problema más grave de cualquier RAG legal: verificar que las
citas jurisprudenciales sean reales. El resto puede esperar.

Cada agente es incremental y opcional. No necesitas todo o nada.
