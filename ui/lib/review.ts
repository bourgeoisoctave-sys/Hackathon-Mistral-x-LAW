import { Check, Minus, X, type LucideIcon } from 'lucide-react'

export type ClauseState = 'presente' | 'partielle' | 'absente'
export type SourceType = 'mail' | 'reunion' | 'note'
export type Exigence = 'standard' | 'max'

export interface OralTrace { citation: string; text: string; source_type: SourceType; date: string }

export interface Clause {
  id: string; libelle: string; etat: ClauseState; cle: boolean; poids: number; pourquoi: string
  extrait_pv: string; traces_orales: OralTrace[]
}

export interface Precedent { source: string; page: number; section_pv: string; text: string; distance: number }

/** Sortie de la brique LLM → réponse (respond.py). Tout est optionnel : l'UI tient sans. */
export interface Reponse {
  resume?: string
  priorites?: string[]
  par_clause?: Record<string, { pourquoi_ici?: string; redaction?: string }>
  questions_suite?: string[]
}

export interface Score { brut: number; malus_cles: number; final: number; cles_manquantes: string[]; exigence: Exigence }

export interface Qualification { forme: string; societe: string; date: string; nature: string; categorie: string; categorie_libelle: string }

export interface Defaut { defaut: string; correction: string }
export interface Revue { version: string; defauts: Defaut[]; revue: string }

export interface CasSimilaire {
  acte_id: string; source: string; societe: string; forme: string; nature: string; date: string
  brut: number; points: number; raisons: string[]; categorie_libelle: string; historique: Revue[]; synthetique: boolean
}

export interface Changement {
  id: string; libelle: string; etat_avant: ClauseState | ''; texte: string; resume: string
  source_precedent: string; source_revue?: string; source_email: string; justification: string; a_verifier: string[]
}

/** Une revue complète, telle que renvoyée par scripts/review.py (live) ou embarquée (démo). */
export interface Review {
  id: string
  pv: string
  dossier: string
  qualification: Qualification
  type_operation: string
  type_libelle: string
  exigence: Exigence
  score: Score
  score_apres: Score
  inchange_pct: number
  reponse: Reponse
  clauses: Clause[]
  precedents: Precedent[]
  cas_similaires: CasSimilaire[]
  changements: Changement[]
  texte_corrige: string
  texte_balise: string
  docx_url: string
  corpus: { actes: number; templates: number; revues?: number; chunks: number }
  live: boolean
}

export const KEY_MALUS = -10

export type Tone = 'critical' | 'caution' | 'success'

export const TONE_CLASSES: Record<Tone, { text: string; soft: string; stroke: string; dot: string }> = {
  critical: { text: 'text-critical-text', soft: 'bg-critical-surface', stroke: 'stroke-critical', dot: 'bg-critical' },
  caution: { text: 'text-caution-text', soft: 'bg-caution-surface', stroke: 'stroke-caution', dot: 'bg-caution' },
  success: { text: 'text-success-text', soft: 'bg-success-surface', stroke: 'stroke-success', dot: 'bg-success' },
}

export const STATE_META: Record<ClauseState, { label: string; icon: LucideIcon; tone: Tone }> = {
  presente: { label: 'Present', icon: Check, tone: 'success' },
  partielle: { label: 'Partial', icon: Minus, tone: 'caution' },
  absente: { label: 'Absent', icon: X, tone: 'critical' },
}

export interface ClauseGroup { id: string; title: string; hint: string; tone: Tone; clauses: Clause[] }

export function groupClauses(clauses: Clause[], score: Score): ClauseGroup[] {
  const missing = new Set(score.cles_manquantes)
  return [
    { id: 'key-missing', title: 'Key clauses missing', hint: `${KEY_MALUS} each`, tone: 'critical' as const, clauses: clauses.filter((c) => missing.has(c.id)) },
    { id: 'other-gaps', title: 'Partial / non-key gaps', hint: 'No penalty', tone: 'caution' as const, clauses: clauses.filter((c) => !missing.has(c.id) && c.etat !== 'presente') },
    { id: 'present', title: 'Present', hint: 'Covered in the draft', tone: 'success' as const, clauses: clauses.filter((c) => !missing.has(c.id) && c.etat === 'presente') },
  ].filter((g) => g.clauses.length > 0)
}

export function scoreTone(score: number): { tone: Tone; label: string } {
  if (score < 40) return { tone: 'critical', label: 'Low' }
  if (score < 70) return { tone: 'caution', label: 'Fair' }
  return { tone: 'success', label: 'Good' }
}

// Même règle que scoring.py : couverture pondérée, puis -10 par clause clé manquante.
const PARTIAL_VALUE: Record<Exigence, number> = { standard: 0.5, max: 0 }

export function computeScore(clauses: Clause[], exigence: Exigence): Score {
  const total = clauses.reduce((s, c) => s + c.poids, 0)
  const value = (c: Clause) => (c.etat === 'presente' ? 1 : c.etat === 'partielle' ? PARTIAL_VALUE[exigence] : 0)
  const brut = total ? Math.round((100 * clauses.reduce((s, c) => s + c.poids * value(c), 0)) / total) : 0
  const cles_manquantes = clauses
    .filter((c) => c.cle && (c.etat === 'absente' || (exigence === 'max' && c.etat === 'partielle')))
    .map((c) => c.id)
  const malus_cles = KEY_MALUS * cles_manquantes.length
  return { brut, malus_cles, final: Math.max(0, brut + malus_cles), cles_manquantes, exigence }
}

/** Segments du PV corrigé : texte conservé et passages modifiés ([[MOD:id]] … [[/MOD]]). */
export type Segment = { kind: 'text'; text: string } | { kind: 'mod'; id: string; text: string }

export function segments(texteBalise: string): Segment[] {
  const out: Segment[] = []
  const re = /\[\[MOD:([a-z_]+)\]\]([\s\S]*?)\[\[\/MOD\]\]/g
  let pos = 0
  for (const m of texteBalise.matchAll(re)) {
    if (m.index! > pos) out.push({ kind: 'text', text: texteBalise.slice(pos, m.index) })
    out.push({ kind: 'mod', id: m[1], text: m[2] })
    pos = m.index! + m[0].length
  }
  if (pos < texteBalise.length) out.push({ kind: 'text', text: texteBalise.slice(pos) })
  return out
}
