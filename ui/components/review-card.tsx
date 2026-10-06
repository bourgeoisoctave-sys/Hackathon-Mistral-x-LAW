"use client";

import { useState } from "react";
import { ChevronDown, MessageSquare } from "lucide-react";
import { cn } from "@/lib/utils";
import { type Clause, type Exigence, type Precedent, type Score, KEY_MALUS, STATE_META, TONE_CLASSES, groupClauses, scoreTone } from "@/lib/review";

function ScoreRing({ value }: { value: number }) {
  const r = 24;
  const c = 2 * Math.PI * r;
  const { tone } = scoreTone(value);
  return (
    <div className="relative size-14 shrink-0">
      <svg viewBox="0 0 56 56" className="size-14 -rotate-90">
        <circle cx="28" cy="28" r={r} className="fill-none stroke-muted" strokeWidth="5" />
        <circle cx="28" cy="28" r={r} strokeWidth="5" strokeLinecap="round" className={cn("fill-none transition-all", TONE_CLASSES[tone].stroke)}
          strokeDasharray={c} strokeDashoffset={c - (c * Math.max(value, 1.5)) / 100} />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center font-mono text-[15px] tabular-nums">{value}</div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-[12px] text-muted-foreground">{label}</span>
      <span className="font-mono text-[14px] tabular-nums">{value}</span>
    </div>
  );
}

function Segmented({ value, onChange }: { value: Exigence; onChange: (v: Exigence) => void }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-[12px] text-muted-foreground">Strictness</span>
      <div role="radiogroup" className="flex rounded-md border bg-background p-0.5 font-mono text-[12px]">
        {(["standard", "max"] as Exigence[]).map((v) => (
          <button key={v} type="button" role="radio" aria-checked={value === v} onClick={() => onChange(v)}
            className={cn("rounded px-2.5 py-1 capitalize transition-colors", value === v ? "bg-brand text-white" : "text-muted-foreground hover:text-foreground")}>
            {v}
          </button>
        ))}
      </div>
    </div>
  );
}

function Chip({ children, tone }: { children: React.ReactNode; tone?: "critical" }) {
  return (
    <span className={cn("rounded-md px-1.5 py-0.5 font-mono text-[11px] tabular-nums", tone === "critical" ? "bg-critical-surface text-critical-text" : "bg-muted text-muted-foreground")}>
      {children}
    </span>
  );
}

export function ReviewCard({
  clauses, score, exigence, onExigence, selected, onSelect, precedents, corpus,
}: {
  clauses: Clause[]; score: Score; exigence: Exigence; onExigence: (e: Exigence) => void;
  selected: Clause | null; onSelect: (c: Clause) => void; precedents: Precedent[]; corpus: { actes: number; templates: number };
}) {
  const [showPrecedents, setShowPrecedents] = useState(false);
  const keyTotal = clauses.filter((c) => c.cle).length;
  const missing = new Set(score.cles_manquantes);
  return (
    <section className="rounded-md border bg-card" aria-label="PV review">
      <header className="flex flex-wrap items-center gap-6 border-b bg-muted/60 px-4 py-4">
        <ScoreRing value={score.final} />
        <Stat label="Score" value={`${score.final} / 100`} />
        <Stat label="Raw" value={`${score.brut}`} />
        <Stat label="Key penalty" value={`${score.malus_cles}`} />
        <Stat label="Key clauses missing" value={`${score.cles_manquantes.length} / ${keyTotal}`} />
        <div className="ml-auto"><Segmented value={exigence} onChange={onExigence} /></div>
      </header>

      <div className="px-2 py-2">
        {groupClauses(clauses, score).map((g) => (
          <div key={g.id} className="py-1">
            <div className="flex items-center gap-2 px-2 py-2 font-mono text-[11px] uppercase tracking-wide text-muted-foreground">
              <span className={cn("size-1.5 rounded-full", TONE_CLASSES[g.tone].dot)} />
              <span className="text-foreground">{g.title}</span>
              <span>· {g.clauses.length}</span>
              <span>· {g.hint}</span>
            </div>
            <ul>
              {g.clauses.map((c) => {
                const meta = STATE_META[c.etat];
                const isSel = selected?.id === c.id;
                return (
                  <li key={c.id}>
                    <button type="button" onClick={() => onSelect(c)} aria-pressed={isSel}
                      className={cn("flex h-10 w-full items-center gap-3 rounded-lg px-2 text-left text-[14px] transition-colors hover:bg-accent", isSel && "bg-accent")}>
                      <span className={cn("size-2 shrink-0 rounded-full", TONE_CLASSES[meta.tone].dot)} aria-hidden />
                      <span className="min-w-0 flex-1 truncate">{c.libelle}</span>
                      <span className="hidden text-[12px] text-muted-foreground sm:inline">{meta.label}</span>
                      {c.cle && <Chip>Key</Chip>}
                      {missing.has(c.id) && <Chip tone="critical">{KEY_MALUS}</Chip>}
                      <Chip>{c.poids} pts</Chip>
                      <span className="flex items-center gap-1 text-[12px] text-muted-foreground"><MessageSquare className="size-3.5" />{c.traces_orales.length}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>

      <footer className="border-t px-4 py-3">
        <button type="button" onClick={() => setShowPrecedents((s) => !s)} aria-expanded={showPrecedents}
          className="flex w-full items-center gap-2 font-mono text-[11px] uppercase tracking-wide text-muted-foreground hover:text-foreground">
          <ChevronDown className={cn("size-3.5 transition-transform", showPrecedents && "rotate-180")} />
          Grounded in {precedents.length} precedents from the firm corpus ({corpus.actes} acts, {corpus.templates} templates)
        </button>
        {showPrecedents && (
          <ul className="mt-3 space-y-2">
            {precedents.map((p, i) => (
              <li key={i} className="rounded-md border bg-muted/40 p-3">
                <div className="flex flex-wrap items-center gap-2 font-mono text-[11px] text-muted-foreground">
                  <span className="text-foreground">{p.source.replace(/^.*\//, "")}</span>
                  <span>p.{p.page}</span>
                  <span>· for « {p.section_pv} »</span>
                </div>
                <p className="mt-1 line-clamp-3 text-[13px] text-muted-foreground">{p.text}</p>
              </li>
            ))}
          </ul>
        )}
      </footer>
    </section>
  );
}
