"use client";

import { Mail, Users } from "lucide-react";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";
import { type Clause, type Reponse, STATE_META, TONE_CLASSES } from "@/lib/review";

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <h3 className="eyebrow">{title}</h3>
      {children}
    </div>
  );
}

export function ClauseSheet({ clause, reponse, onClose }: { clause: Clause | null; reponse: Reponse; onClose: () => void }) {
  const meta = clause ? STATE_META[clause.etat] : null;
  const llm = clause ? reponse.par_clause?.[clause.id] : undefined;
  return (
    <Sheet open={!!clause} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full gap-0 overflow-y-auto border-l p-0 sm:max-w-[460px]">
        {clause && meta && (
          <>
            <SheetHeader className="border-b bg-muted/60 px-5 py-4">
              <div className="flex items-center gap-2 font-mono text-[11px]">
                <span className={cn("rounded-md px-1.5 py-0.5", TONE_CLASSES[meta.tone].soft, TONE_CLASSES[meta.tone].text)}>{meta.label}</span>
                {clause.cle && <span className="rounded-md bg-muted px-1.5 py-0.5 text-muted-foreground">Key clause</span>}
                <span className="rounded-md bg-muted px-1.5 py-0.5 text-muted-foreground">{clause.poids} pts</span>
              </div>
              <SheetTitle className="text-[15px] font-semibold leading-snug">{clause.libelle}</SheetTitle>
              <SheetDescription className="sr-only">Clause details, oral traces and suggested wording</SheetDescription>
            </SheetHeader>

            <div className="space-y-6 px-5 py-5 text-[14px] leading-relaxed">
              {llm?.pourquoi_ici && (
                <Block title="Why it matters in this matter">
                  <p className="rounded-md border-l-2 border-brand-mid bg-brand-soft/40 px-3 py-2">{llm.pourquoi_ici}</p>
                </Block>
              )}

              <Block title="Why it matters in general">
                <p className="text-muted-foreground">{clause.pourquoi}</p>
              </Block>

              <Block title="Found in the PV">
                {clause.extrait_pv ? (
                  <blockquote className="rounded-md bg-muted px-3 py-2 text-[13px] italic text-muted-foreground">“{clause.extrait_pv}”</blockquote>
                ) : (
                  <p className="text-muted-foreground">Not found in the draft.</p>
                )}
              </Block>

              <Block title="What was said in the matter">
                {clause.traces_orales.length === 0 && <p className="text-muted-foreground">No trace in the matter's emails or meetings.</p>}
                <ul className="space-y-2">
                  {clause.traces_orales.map((t, i) => {
                    const Icon = t.source_type === "mail" ? Mail : Users;
                    return (
                      <li key={i} className="rounded-md border p-3">
                        <div className="flex items-start gap-2">
                          <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-sm bg-muted"><Icon className="size-3.5" /></span>
                          <div className="min-w-0">
                            <p className="truncate font-mono text-[12px]" title={t.citation}>{t.citation}</p>
                            <p className="mt-1 text-[13px] italic text-muted-foreground">“{t.text}”</p>
                          </div>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </Block>

              {llm?.redaction && (
                <Block title="Suggested wording">
                  <pre className="whitespace-pre-wrap rounded-md border bg-muted/40 p-3 font-sans text-[13px] leading-relaxed">{llm.redaction}</pre>
                </Block>
              )}
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
