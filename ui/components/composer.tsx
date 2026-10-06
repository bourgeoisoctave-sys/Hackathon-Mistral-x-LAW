"use client";

import { useRef, useState } from "react";
import { ArrowUp, FileUp, PenLine, Plus, X } from "lucide-react";
import { DocCubes, foundDurationMs, type DocPhase, type FoundDoc } from "@/components/doc-cubes";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useReview } from "@/components/review-provider";
import type { Exigence } from "@/lib/review";

const MIN_SEARCH_MS = 1200; // l'amas tourne au moins ce temps, même si la base répond plus vite

/** Barre de contexte : [+] importer un brouillon (défaut) ou demander un brouillon ; question → recherche dans la base (/api/search). */
export function Composer({ exigence }: { exigence: Exigence }) {
  const { importDraft, reviewing } = useReview();
  const input = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [phase, setPhase] = useState<DocPhase | null>(null);
  const [docs, setDocs] = useState<FoundDoc[]>([]);
  const [error, setError] = useState("");
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  const reset = () => { timers.current.forEach(clearTimeout); timers.current = []; setPhase(null); setDocs([]); setError(""); };

  async function search() {
    const q = question.trim();
    if (!q || reviewing || (phase && phase !== "done")) return;
    reset();
    setPhase("searching");
    const t0 = Date.now();
    try {
      const res = await fetch("/api/search", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ q }) });
      const data = (await res.json()) as { docs?: FoundDoc[]; error?: string };
      if (!res.ok || data.error) throw new Error(data.error ?? "La recherche a échoué.");
      const found = data.docs ?? [];
      await new Promise((r) => setTimeout(r, Math.max(0, MIN_SEARCH_MS - (Date.now() - t0))));
      setDocs(found);
      if (found.length === 0) { setPhase("done"); return; }
      setPhase("found");
      const implodeAt = foundDurationMs(found.length) + 500;
      timers.current = [setTimeout(() => setPhase("imploding"), implodeAt), setTimeout(() => setPhase("done"), implodeAt + 900)];
    } catch (e) {
      setPhase(null);
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="sticky bottom-0 bg-gradient-to-t from-background via-background to-transparent px-5 pb-4 pt-6">
      <div className="mx-auto w-full max-w-[900px] rounded-xl border bg-background p-3">
        {(phase || error) && (
          <div className="relative mb-2 px-1">
            {phase === "done" && (
              <button type="button" aria-label="Close" onClick={reset} className="absolute right-1 top-1 z-10 rounded-md p-1 text-muted-foreground hover:bg-muted">
                <X className="size-4" />
              </button>
            )}
            {phase && <DocCubes phase={phase} docs={docs} />}
            {error && <p className="font-mono text-[12px] text-critical-text">{error}</p>}
          </div>
        )}
        <Textarea disabled={reviewing} value={question} onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void search(); } }}
          placeholder={reviewing ? "Reviewing…" : "Search the firm's documents… (e.g. pouvoirs pour les formalités)"}
          className="min-h-[48px] resize-none border-0 bg-transparent px-2 text-[15px] shadow-none placeholder:text-[#8a8a8a] focus-visible:ring-0" />
        <div className="flex items-center justify-between px-1 pt-1">
          <div className="relative">
            <Button variant="outline" size="icon" className="size-9 rounded-lg shadow-none" aria-label="Add to the workspace" aria-expanded={open}
              disabled={reviewing} onClick={() => setOpen((o) => !o)}>
              <Plus className="size-4" />
            </Button>
            {open && (
              <div role="menu" className="absolute bottom-11 left-0 z-10 w-[300px] rounded-lg border bg-background p-1 shadow-[0_4px_16px_rgba(0,0,0,0.08)]">
                <button type="button" role="menuitem" className="flex w-full items-start gap-3 rounded-md px-3 py-2 text-left hover:bg-muted"
                  onClick={() => { setOpen(false); input.current?.click(); }}>
                  <FileUp className="mt-0.5 size-4 shrink-0" />
                  <span>
                    <span className="block text-[14px] font-medium">Import a draft</span>
                    <span className="block text-[12px] text-muted-foreground">PDF or .docx · reviewed against the firm&apos;s precedents</span>
                  </span>
                  <span className="ml-auto rounded-sm bg-brand px-1 font-mono text-[10px] text-white">default</span>
                </button>
                <button type="button" role="menuitem" disabled className="flex w-full items-start gap-3 rounded-md px-3 py-2 text-left opacity-50">
                  <PenLine className="mt-0.5 size-4 shrink-0" />
                  <span>
                    <span className="block text-[14px] font-medium">Ask for a draft from a brief</span>
                    <span className="block text-[12px] text-muted-foreground">Soon</span>
                  </span>
                </button>
              </div>
            )}
            <input ref={input} type="file" accept=".pdf,.docx" className="hidden"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) void importDraft(f, exigence); e.target.value = ""; }} />
          </div>
          <div className="flex items-center gap-3">
            <span className="font-mono text-[11px] text-muted-foreground">strictness: {exigence}</span>
            <Button size="icon" disabled={reviewing || !question.trim() || (!!phase && phase !== "done")} onClick={() => void search()}
              className="size-9 rounded-lg bg-brand text-white" aria-label="Send"><ArrowUp className="size-4" /></Button>
          </div>
        </div>
      </div>
    </div>
  );
}
