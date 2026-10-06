"use client";

import { useRef } from "react";
import { FileUp, PenLine } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useReview } from "@/components/review-provider";
import type { Exigence } from "@/lib/review";

const STEPS = [
  ["01", "Qualify", "operation type, legal form, date"],
  ["02", "Find", "the 3 closest precedents and what the partner corrected on them"],
  ["03", "Correct", "only the missing clauses, from those precedents"],
  ["04", "Deliver", "the corrected file, score before → after, every change sourced"],
];

export function EmptyState({ exigence, onExigence }: { exigence: Exigence; onExigence: (e: Exigence) => void }) {
  const { importDraft, loadDemo, reviewing, error, clearError } = useReview();
  const input = useRef<HTMLInputElement>(null);
  return (
    <div className="mx-auto flex w-full max-w-[760px] flex-col gap-8 px-5 pb-44 pt-20">
      <div>
        <p className="eyebrow">New workspace</p>
        <h1 className="mt-3 text-[32px] font-semibold leading-[1.1]">Import a draft. Get it corrected against what the firm actually does.</h1>
        <p className="mt-3 text-[15px] leading-relaxed text-muted-foreground">
          Thread reads your PV, finds the closest precedents in the firm&apos;s corpus, and rewrites only the missing clauses, each with its source.
        </p>
      </div>

      <div className="rounded-md border p-5">
        <div className="flex flex-wrap items-center gap-3">
          <Button className="h-11 rounded-lg bg-brand px-5 text-[15px] text-white hover:bg-brand/90" disabled={reviewing} onClick={() => input.current?.click()}>
            <FileUp className="size-4" /> Import a draft (PDF, .docx)
          </Button>
          <Button variant="outline" className="h-11 rounded-lg px-5 text-[15px] font-normal shadow-none" disabled>
            <PenLine className="size-4" /> Ask for a draft from a brief
          </Button>
          <div className="ml-auto flex items-center gap-2">
            <span className="text-[12px] text-muted-foreground">Strictness</span>
            <div role="radiogroup" className="flex rounded-md border bg-background p-0.5 font-mono text-[12px]">
              {(["standard", "max"] as Exigence[]).map((v) => (
                <button key={v} type="button" role="radio" aria-checked={exigence === v} onClick={() => onExigence(v)}
                  className={`rounded px-2.5 py-1 capitalize ${exigence === v ? "bg-brand text-white" : "text-muted-foreground hover:text-foreground"}`}>{v}</button>
              ))}
            </div>
          </div>
        </div>
        <input ref={input} type="file" accept=".pdf,.docx" className="hidden"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) void importDraft(f, exigence); e.target.value = ""; }} />
        {error && (
          <div className="mt-4 rounded-md border border-critical-border bg-critical-surface p-3 font-mono text-[12px] text-critical-text">
            <pre className="whitespace-pre-wrap">{error}</pre>
            <button type="button" className="mt-2 underline" onClick={clearError}>dismiss</button>
          </div>
        )}
        <p className="mt-4 font-mono text-[12px] text-muted-foreground">
          About 2 minutes per review. No draft at hand? <button type="button" className="underline hover:text-foreground" onClick={loadDemo}>Load the demo review</button>.
        </p>
      </div>

      <div className="grid gap-px overflow-hidden rounded-md border bg-border sm:grid-cols-2">
        {STEPS.map(([n, title, text]) => (
          <div key={n} className="bg-background p-4">
            <span className="font-mono text-[12px] text-muted-foreground">{n}</span>
            <p className="mt-1 text-[15px] font-semibold">{title}</p>
            <p className="text-[13px] text-muted-foreground">{text}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
