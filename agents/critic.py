"""
CRITIC AGENT — Verificador de Citas Jurisprudenciales
=====================================================
Post-procesa la respuesta del Legal Writer y verifica que
cada cita jurisprudencial corresponda a un documento real
en el corpus. Detecta alucinaciones en citas.

Fase 1: Warn-only (marca problemas, no bloquea)
Fase 2+: Re-escritura automática
"""
import os
import re
import json
from core.config import logger, METADATA_DOCS_PATH


class Citation:
    """Representa una cita extraída de la respuesta."""
    def __init__(self, doc_id=None, identificador=None, texto_cita=None,
                 source_file=None, linea=None):
        self.doc_id = doc_id              # ej: "1612215.html"
        self.identificador = identificador  # ej: "CAS. N° 15-2015 LAMBAYEQUE"
        self.texto_cita = texto_cita      # texto exacto como aparece
        self.source_file = source_file    # archivo HTML referenciado
        self.linea = linea                # línea aprox en la respuesta
        self.exists_in_corpus = None      # resultado de verificación
        self.was_in_context = None        # estaba en los docs recuperados?
        self.hallucinated = None          # veredicto final


class Verdict:
    """Resultado de la verificación del Critic."""
    def __init__(self, passed=True, citations=None, errors=None, warnings=None,
                 score=1.0, action="accept"):
        self.passed = passed
        self.citations = citations or []
        self.errors = errors or []
        self.warnings = warnings or []
        self.score = score               # 0.0 = terrible, 1.0 = perfecto
        self.action = action             # accept, warn, re-rewrite

    def to_dict(self):
        return {
            "passed": self.passed,
            "score": self.score,
            "action": self.action,
            "total_citations": len(self.citations),
            "hallucinated": sum(1 for c in self.citations if c.hallucinated),
            "verified": sum(1 for c in self.citations if not c.hallucinated and c.exists_in_corpus),
            "unverifiable": sum(1 for c in self.citations if c.exists_in_corpus is None),
            "errors": self.errors,
            "citations": [
                {
                    "doc_id": c.doc_id,
                    "identificador": c.identificador,
                    "exists_in_corpus": c.exists_in_corpus,
                    "was_in_context": c.was_in_context,
                    "hallucinated": c.hallucinated
                }
                for c in self.citations
            ]
        }


class CriticAgent:
    """
    Agente crítico que verifica citas jurisprudenciales en respuestas RAG.

    Uso:
        critic = CriticAgent()
        verdict = critic.verify(respuesta_texto, context_doc_ids)
        if not verdict.passed:
            print(f"⚠️ {len(verdict.errors)} citas sospechosas")
    """

    def __init__(self):
        self.metadata = {}        # doc_id -> {identificador, organo, ...}
        self.id2doc = {}          # identificador normalizado -> doc_id
        self._loaded = False

    def _load_metadata(self):
        """Carga metadata_docs.json y los nuevos JSONs de Groq Batch."""
        if self._loaded:
            return
        
        # Cargar metadata original (HTMLs)
        path = METADATA_DOCS_PATH
        if path and os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    self.metadata = json.load(f)
                for doc_id, meta in self.metadata.items():
                    id_str = meta.get("identificador", "")
                    if id_str:
                        norm = self._normalize_id(id_str)
                        self.id2doc[norm] = doc_id
                    doc_clean = doc_id.replace(".html", "")
                    self.id2doc[doc_clean] = doc_id
                logger.info(f"✅ Critic: {len(self.metadata)} docs HTML cargados")
            except Exception as e:
                logger.warning(f"⚠️ Critic: error cargando metadata: {e}")
        
        # Cargar nuevos documentos de Groq Batch (JSON)
        import glob as _glob
        groq_files = sorted(_glob.glob("data_raw/rag_listo_batch_groq_*.json"))
        if groq_files:
            groq_count = 0
            for gf in groq_files:
                try:
                    with open(gf, 'r', encoding='utf-8') as f:
                        docs = json.load(f)
                    for doc in docs:
                        did = doc.get("id_documento", "")
                        if did:
                            self.id2doc[did] = did
                            groq_count += 1
                except Exception as e:
                    logger.warning(f"⚠️ Critic: error cargando {gf}: {e}")
            logger.info(f"✅ Critic: {groq_count} docs Groq Batch cargados")
        
        self._loaded = True

    def _normalize_id(self, s):
        """Normaliza un identificador para búsqueda fuzzy."""
        s = s.upper().strip()
        s = re.sub(r'\s+', ' ', s)      # espacios múltiples → simple
        s = re.sub(r'[°º]', '', s)      # quitar símbolos de grado
        s = re.sub(r'[.\-\s]', '', s)   # quitar puntos, guiones, espacios
        return s

    def extract_citations(self, response_text):
        """
        Extrae todas las citas jurisprudenciales de la respuesta.
        Delega en métodos por patrón de regex.
        """
        citations = []
        citations += self._citar_jurisprudencia_path(response_text)
        citations += self._citar_exp(response_text)
        citations += self._citar_cas(response_text)
        citations += self._citar_rtf(response_text)
        citations += self._citar_html_suelto(response_text)
        citations += self._citar_numeros_docid(response_text)
        citations += self._citar_leyes(response_text)
        return self._deduplicar(citations)

    # ── Patrones de extracción ─────────────────────────

    def _citar_jurisprudencia_path(self, text):
        """Pattern 1: Jurisprudencia/1612215.html"""
        out = []
        for m in re.finditer(r'Jurisprudencia/([\w]+\.html)', text):
            out.append(Citation(doc_id=m.group(1), texto_cita=m.group(0),
                                source_file=m.group(1),
                                linea=text[:m.start()].count('\n') + 1))
        return out

    def _citar_exp(self, text):
        """Pattern 2: EXP. N.º XXXX o EXP. N° XXXX"""
        out = []
        for m in re.finditer(
            r'(?:EXP|Expediente)\s*[\.:]*\s*N[°º\.]*\s*[\.:]*\s*(\d+(?:[-\s]\d+)*)',
            text, re.IGNORECASE
        ):
            out.append(Citation(identificador=f"EXP. N° {m.group(1).strip()}",
                                texto_cita=m.group(0),
                                linea=text[:m.start()].count('\n') + 1))
        return out

    def _citar_cas(self, text):
        """Pattern 3: CAS. N° XXXX"""
        out = []
        for m in re.finditer(
            r'CAS[\.\s]*N[°º\.]*\s*[\.:]*\s*(\d+(?:[-\s]\d+[-\s][A-ZÁÉÍÓÚ\s]+)?)',
            text, re.IGNORECASE
        ):
            out.append(Citation(identificador=f"CAS. N° {m.group(1).strip()}",
                                texto_cita=m.group(0),
                                linea=text[:m.start()].count('\n') + 1))
        return out

    def _citar_rtf(self, text):
        """Pattern 4: RTF N° XXXX"""
        out = []
        for m in re.finditer(
            r'RTF[\.\s]*N[°º\.]*\s*[\.:]*\s*(\d+(?:[-\s]\d+)*)',
            text, re.IGNORECASE
        ):
            out.append(Citation(identificador=f"RTF N° {m.group(1).strip()}",
                                texto_cita=m.group(0),
                                linea=text[:m.start()].count('\n') + 1))
        return out

    def _citar_html_suelto(self, text):
        """Pattern 5: doc_id suelto (XXXX.html)"""
        out = []
        for m in re.finditer(r'(\d+\.html)', text):
            doc_id = m.group(1)
            if not any(c.doc_id == doc_id for c in out):
                out.append(Citation(doc_id=doc_id, texto_cita=m.group(0),
                                    source_file=doc_id,
                                    linea=text[:m.start()].count('\n') + 1))
        return out

    def _citar_numeros_docid(self, text):
        """Pattern 6: Números de 6-7 dígitos que parecen doc_ids (ej: 1308950)"""
        out = []
        for m in re.finditer(r'(?<!\d)(\d{6,7})(?!\d)', text):
            num = m.group(1)
            doc_candidate = f"{num}.html"
            if any(c.doc_id == doc_candidate for c in out):
                continue
            out.append(Citation(doc_id=doc_candidate, texto_cita=m.group(0),
                                linea=text[:m.start()].count('\n') + 1))
        return out

    def _citar_leyes(self, text):
        """Pattern 7: Leyes, Decretos y Codigos citados"""
        out = []
        for m in re.finditer(
            r'(Ley\s*[N°º\.]+\s*\d+(?:[-\s]\d+)*|'
            r'D\.?L\.?\s*[N°º\.]*\s*\d+(?:[-\s]\d+)*|'
            r'Decreto\s+(Legislativo|Supremo|de\s+Urgencia)\s*[N°º\.]*\s*\d+(?:[-\s]\d+)*|'
            r'Codigo\s+(Civil|Procesal\s+Civil|Penal|Tributario|del\s+Trabajo|'
            r'de\s+Comercio|de\s+los\s+Ninos|del\s+Ambiente))',
            text, re.IGNORECASE
        ):
            ident = re.sub(r'\s+', ' ', m.group(0).strip())
            out.append(Citation(identificador=ident, texto_cita=m.group(0),
                                linea=text[:m.start()].count('\n') + 1))
        return out

    # ── Utilidades ─────────────────────────────────────

    def _deduplicar(self, citations):
        """Elimina citas duplicadas por (doc_id, identificador)."""
        seen = set()
        unicos = []
        for c in citations:
            key = (c.doc_id, c.identificador)
            if key not in seen:
                seen.add(key)
                unicos.append(c)
        return unicos

    def verify_citations(self, citations, context_doc_ids=None):
        """
        Verifica cada cita contra el corpus.

        Args:
            citations: List[Citation] — citas extraídas
            context_doc_ids: List[str] — doc_ids que se dieron como contexto

        Returns:
            List[Citation] — mismas citas con campos de verificación llenos
        """
        self._load_metadata()

        if context_doc_ids is None:
            context_doc_ids = set()
        else:
            context_doc_ids = set(context_doc_ids)

        for c in citations:
            # 1. Verificar por doc_id directo
            if c.doc_id:
                c.exists_in_corpus = c.doc_id in self.metadata
                c.was_in_context = c.doc_id in context_doc_ids
            else:
                c.exists_in_corpus = False
                c.was_in_context = False

            # 2. Si no se encontró por doc_id, buscar por identificador
            if not c.exists_in_corpus and c.identificador:
                norm = self._normalize_id(c.identificador)
                if norm in self.id2doc:
                    matched_doc_id = self.id2doc[norm]
                    c.doc_id = matched_doc_id
                    c.exists_in_corpus = True
                    c.was_in_context = matched_doc_id in context_doc_ids
                # NOTA: Sin fuzzy match — solo coincidencias exactas
                # para evitar falsos positivos. Si se necesitan más matches,
                # implementar búsqueda por número de expediente en una Fase 2.

            # 3. Veredicto final
            if c.doc_id:
                # Tenemos un doc_id concreto → podemos verificar
                c.hallucinated = not c.exists_in_corpus
                # Ademas, si existe pero NO estaba en el contexto entregado, es sospechoso
                if c.exists_in_corpus and not c.was_in_context:
                    c.hallucinated = True  # Existe pero no se uso como contexto = alucinacion
            else:
                # Solo tenemos identificador textual (EXP. N°, CAS. N°, Ley...)
                # Si no encontramos el identificador en el corpus, es alucinacion
                # Si existe pero no estaba en contexto, tambien
                if c.identificador:
                    norm = self._normalize_id(c.identificador)
                    if norm in self.id2doc:
                        c.doc_id = self.id2doc[norm]
                        c.exists_in_corpus = True
                        c.was_in_context = c.doc_id in context_doc_ids
                        c.hallucinated = not c.was_in_context
                    elif "CODIGO" in norm or "LEY" in norm or "D.L." in norm or "DECRETO" in norm:
                        # Leyes y codigos: si no estan en corpus, son sospechosas
                        c.hallucinated = True
                    else:
                        c.hallucinated = True
                else:
                    c.hallucinated = False  # Indeterminado, sin identificador

        return citations

    def score_verdict(self, citations, strict=False):
        """
        Produce un veredicto basado en las verificaciones.

        Args:
            citations: List[Citation] — citas verificadas
            strict: bool — si True, cualquier warning es error

        Returns:
            Verdict
        """
        total = len(citations)
        hallu = [c for c in citations if c.hallucinated]
        verified = [c for c in citations if c.exists_in_corpus and not c.hallucinated]
        unverifiable = [c for c in citations if c.exists_in_corpus is None]
        not_in_context = [c for c in citations if not c.was_in_context and c.exists_in_corpus and not c.hallucinated]

        errors = []
        warnings = []

        for c in hallu:
            if c.doc_id:
                errors.append(f"'{c.doc_id}' no existe en el corpus")
            elif c.identificador:
                errors.append(f"'{c.identificador}' no existe en el corpus")
            else:
                errors.append("Cita no identificable")

        for c in not_in_context:
            warnings.append(f"'{c.doc_id}' existe pero NO estaba en el contexto recuperado")

        # Score: proporción de citas verificables que son correctas
        verificables = [c for c in citations if c.exists_in_corpus is not None]
        total_verificables = len(verificables)
        if total_verificables == 0:
            # Sin citas verificables = nada que revisar = 100%
            score = 1.0
        else:
            correctas = sum(1 for c in verificables if not c.hallucinated and c.exists_in_corpus)
            score = correctas / total_verificables

        if errors and strict:
            return Verdict(
                passed=False,
                citations=citations,
                errors=errors,
                warnings=warnings,
                score=score,
                action="re-rewrite"  # En Fase 2+
            )
        elif errors:
            return Verdict(
                passed=False,
                citations=citations,
                errors=errors,
                warnings=warnings,
                score=score,
                action="warn"  # Fase 1: solo advertir
            )
        else:
            return Verdict(
                passed=True,
                citations=citations,
                errors=[],
                warnings=warnings,
                score=score,
                action="accept"
            )

    def verify(self, response_text, context_doc_ids=None, strict=False):
        """
        Pipeline completo: extraer → verificar → puntuar.

        Args:
            response_text: str — respuesta del LLM
            context_doc_ids: list[str] — doc_ids que se usaron como contexto
            strict: bool — modo estricto (re-rewrite)

        Returns:
            Verdict
        """
        citations = self.extract_citations(response_text)
        if not citations:
            # Sin citas: puede ser normal (respuesta corta, saludo, etc.)
            return Verdict(
                passed=True,
                citations=[],
                warnings=[],
                score=1.0,
                action="accept"
            )

        citations = self.verify_citations(citations, context_doc_ids)
        return self.score_verdict(citations, strict=strict)
