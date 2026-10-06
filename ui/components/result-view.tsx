"use client";

import { useMemo, useState } from "react";
import { ChevronDown, Download, FileText, Mail, Scale } from "lucide-react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { ClauseSheet } from "@/components/clause-sheet";
import { ReviewCard } from "@/components/review-card";
import { cn } from "@/lib/utils";
import { type CasSimilaire, type Changement, type Clause, type Exigence, type Review, TONE_CLASSES, computeScore, scoreTone, segments } from "@/lib/review";

/** Le LLM renvoie parfois du `**gras**` : on le rend, sans dépendance markdown. */
function renderBold(text: string) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") ? <strong key={i} className="font-semibold">{part.slice(2, -2)}</strong> : part,
  );
}

function ScoreRing({ value, size = 56 }: { value: number; size?: number }) {
  const r = 24, c = 2 * Math.PI * r;
  const { tone } = scoreTone(value);
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg viewBox="0 0 56 56" className="-rotate-90" style={{ width: size, height: size }}>
        <circle cx="28" cy="28" r={r} className="fill-none stroke-muted" strokeWidth="5" />
        <circle cx="28" cy="28" r={r} strokeWidth="5" strokeLinecap="round" className={cn("fill-none", TONE_CLASSES[tone].stroke)} strokeDasharray={c} strokeDashoffset={c - (c * Math.max(value, 1.5)) / 100} />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center font-mono text-[15px] tabular-nums">{value}</div>
    </div>
  );
}

function CaseCard({ c }: { c: CasSimilaire }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-md border bg-background">
      <div className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="truncate text-[15px] font-semibold">{c.societe || c.acte_id}</p>
            <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">{[c.forme, c.nature, c.date].filter(Boolean).join(" · ")}</p>
          </div>
          <span className="shrink-0 rounded-md bg-muted px-1.5 py-0.5 font-mono text-[11px] tabular-nums text-muted-foreground">coverage {c.brut}</span>
        </div>
        <ul className="mt-3 flex flex-wrap gap-1.5">
          {c.raisons.slice(0, 4).map((r) => <li key={r} className="rounded-sm bg-brand-soft px-1.5 py-0.5 text-[12px] text-white">{r}</li>)}
        </ul>
      </div>
      {c.historique.length > 0 && (
        <div className="border-t">
          <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open}
            className="flex w-full items-center gap-2 px-4 py-2.5 font-mono text-[11px] uppercase tracking-wide text-muted-foreground hover:text-foreground">
            <ChevronDown className={cn("size-3.5 transition-transform", open && "rotate-180")} />
            What the partner corrected on this act
            <span className="ml-auto rounded-sm bg-muted px-1 normal-case tracking-normal">synthetic history</span>
          </button>
          {open && (
            <div className="space-y-3 px-4 pb-4">
              {c.historique.map((h) => (
                <div key={h.version}>
                  <p className="font-mono text-[11px] text-muted-foreground">Review of {h.version}</p>
                  <p className="mt-1 text-[13px] italic leading-relaxed text-muted-foreground">“{h.revue.slice(0, 420)}{h.revue.length > 420 ? "…" : ""}”</p>
                  {h.defauts.length > 0 && (
                    <ul className="mt-2 space-y-1.5">
                      {h.defauts.slice(0, 4).map((d, i) => (
                        <li key={i} className="rounded-md bg-muted/60 p-2 text-[13px]">
                          <span className="text-critical-text">{d.defaut}</span>
                          {d.correction && <span className="block text-success-text">→ {d.correction}</span>}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ChangeSheet({ change, onClose }: { change: Changement | null; onClose: () => void }) {
  return (
    <Sheet open={!!change} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full gap-0 overflow-y-auto border-l p-0 sm:max-w-[460px]">
        {change && (
          <>
            <SheetHeader className="border-b bg-muted/60 px-5 py-4">
              <div className="flex items-center gap-2 font-mono text-[11px]">
                <span className="rounded-md bg-brand px-1.5 py-0.5 text-white">modified</span>
                {change.etat_avant && <span className="rounded-md bg-muted px-1.5 py-0.5 text-muted-foreground">was {change.etat_avant}</span>}
              </div>
              <SheetTitle className="text-[15px] font-semibold leading-snug">{change.libelle}</SheetTitle>
              <SheetDescription className="sr-only">Change details and sources</SheetDescription>
            </SheetHeader>
            <div className="space-y-6 px-5 py-5 text-[14px] leading-relaxed">
              <div><h3 className="eyebrow">What changed</h3><p className="mt-2">{change.resume}</p></div>
              {change.justification && <div><h3 className="eyebrow">Why</h3><p className="mt-2 text-muted-foreground">{change.justification}</p></div>}
              <div>
                <h3 className="eyebrow">Sources</h3>
                <ul className="mt-2 space-y-2">
                  {change.source_precedent && <li className="flex gap-2 rounded-md border p-3 text-[13px]"><Scale className="mt-0.5 size-4 shrink-0" /><span><span className="font-mono text-[11px] text-muted-foreground">Precedent</span><br />{change.source_precedent}</span></li>}
                  {change.source_revue && <li className="flex gap-2 rounded-md border p-3 text-[13px]"><FileText className="mt-0.5 size-4 shrink-0" /><span><span className="font-mono text-[11px] text-muted-foreground">Partner&apos;s review (synthetic history)</span><br />{change.source_revue}</span></li>}
                  {change.source_email && <li className="flex gap-2 rounded-md border p-3 text-[13px]"><Mail className="mt-0.5 size-4 shrink-0" /><span><span className="font-mono text-[11px] text-muted-foreground">Matter email</span><br />{change.source_email}</span></li>}
                  {!change.source_precedent && !change.source_revue && !change.source_email && <li className="text-muted-foreground">No source given.</li>}
                </ul>
              </div>
              {change.a_verifier.length > 0 && (
                <div className="rounded-md border border-caution-border bg-caution-surface p-3 text-[13px] text-caution-text">
                  <span className="font-mono text-[11px] uppercase">To verify</span> — facts not found in the draft nor in any source: {change.a_verifier.join(", ")}
                </div>
              )}
              <div><h3 className="eyebrow">New wording</h3><pre className="mt-2 whitespace-pre-wrap rounded-md border bg-muted/40 p-3 font-sans text-[13px] leading-relaxed">{change.texte}</pre></div>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

export function ResultView({ review }: { review: Review }) {
  const [exigence, setExigence] = useState<Exigence>(review.exigence);
  const [clause, setClause] = useState<Clause | null>(null);
  const [change, setChange] = useState<Changement | null>(null);
  const [showGrid, setShowGrid] = useState(false);
  const score = useMemo(() => (exigence === review.exigence ? review.score : computeScore(review.clauses, exigence)), [review, exigence]);
  const segs = useMemo(() => segments(review.texte_balise), [review.texte_balise]);
  const byId = useMemo(() => new Map(review.changements.map((c) => [c.id, c])), [review.changements]);
  const q = review.qualification;
  const toVerify = review.changements.reduce((n, c) => n + c.a_verifier.length, 0);

  return (
    <div className="mx-auto flex w-full max-w-[900px] flex-col gap-8 px-5 pb-44 pt-10">
      {/* Message du junior */}
      <div className="flex items-start justify-end gap-3">
        <div className="max-w-[640px] rounded-xl bg-muted px-4 py-3 text-[15px] leading-relaxed">
          <p>Here is my draft. Can you correct it against what the firm actually does on this kind of operation?</p>
          <div className="mt-3 inline-flex items-center gap-2 rounded-md border bg-background px-3 py-2 text-[13px]"><FileText className="size-4 text-muted-foreground" /><span className="font-medium">{review.pv}</span></div>
        </div>
        <Avatar className="size-8"><AvatarFallback className="bg-foreground text-[12px] text-background">L</AvatarFallback></Avatar>
      </div>

      {/* Réponse */}
      <div className="space-y-6 text-[15px] leading-[1.65]">
        <p className="eyebrow">{[q.societe, q.forme, q.categorie_libelle || review.type_libelle, q.date].filter(Boolean).join(" · ")}</p>
        {review.reponse.resume && <p>{renderBold(review.reponse.resume)}</p>}

        {/* Score avant → après */}
        <section className="flex flex-wrap items-center gap-6 rounded-md border bg-muted/60 px-5 py-4">
          <div className="flex items-center gap-3"><ScoreRing value={review.score.final} /><div><p className="text-[12px] text-muted-foreground">Your draft</p><p className="font-mono text-[14px]">{review.score.final} / 100</p></div></div>
          <span className="text-muted-foreground">→</span>
          <div className="flex items-center gap-3"><ScoreRing value={review.score_apres.final} /><div><p className="text-[12px] text-muted-foreground">Corrected file</p><p className="font-mono text-[14px]">{review.score_apres.final} / 100</p></div></div>
          <div className="ml-auto flex flex-col items-end gap-2">
            <Button className="h-9 rounded-lg bg-brand px-3 text-white hover:bg-brand/90" nativeButton={false} render={<a href={review.docx_url} download />}>
              <Download className="size-4" /> Download the corrected .docx
            </Button>
            <p className="font-mono text-[11px] text-muted-foreground">{review.inchange_pct}% of your text kept · {review.changements.length} changes · {toVerify} to verify</p>
          </div>
        </section>

        {/* Cas similaires */}
        <section>
          <p className="eyebrow">The {review.cas_similaires.length} closest precedents</p>
          <div className="mt-3 grid gap-3 md:grid-cols-3">{review.cas_similaires.map((c) => <CaseCard key={c.acte_id} c={c} />)}</div>
        </section>

        {/* PV corrigé */}
        <section>
          <p className="eyebrow">Corrected draft · highlighted passages were rewritten, click one for its sources</p>
          <article className="mt-3 rounded-md border bg-background p-6 text-[14px] leading-[1.7]">
            {segs.map((s, i) =>
              s.kind === "text"
                ? s.text.split("\n").map((p, j) => (p.trim() ? <p key={`${i}-${j}`} className="mb-2 whitespace-pre-wrap">{p}</p> : null))
                : (
                  <button key={i} type="button" onClick={() => setChange(byId.get(s.id) ?? { id: s.id, libelle: s.id, etat_avant: "", texte: s.text, resume: "", source_precedent: "", source_email: "", justification: "", a_verifier: [] })}
                    className="mb-2 block w-full rounded-sm border-l-2 border-brand-mid bg-brand-soft/60 px-3 py-1.5 text-left whitespace-pre-wrap transition-colors hover:bg-brand-soft">
                    {s.text.trim()}
                  </button>
                ),
            )}
          </article>
        </section>

        {/* Grille, repliée */}
        <section className="rounded-md border">
          <button type="button" onClick={() => setShowGrid((s) => !s)} aria-expanded={showGrid}
            className="flex w-full items-center gap-2 px-4 py-3 font-mono text-[11px] uppercase tracking-wide text-muted-foreground hover:text-foreground">
            <ChevronDown className={cn("size-3.5 transition-transform", showGrid && "rotate-180")} />
            Expected clauses grid · {score.cles_manquantes.length} key clauses missing in your draft
          </button>
          {showGrid && (
            <div className="border-t p-3">
              <ReviewCard clauses={review.clauses} score={score} exigence={exigence} onExigence={setExigence} selected={clause} onSelect={setClause} precedents={review.precedents} corpus={review.corpus} />
            </div>
          )}
        </section>
      </div>

      <ClauseSheet clause={clause} reponse={review.reponse} onClose={() => setClause(null)} />
      <ChangeSheet change={change} onClose={() => setChange(null)} />
    </div>
  );
}
