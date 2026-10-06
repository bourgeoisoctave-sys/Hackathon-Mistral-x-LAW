"use client";

import { useEffect, useRef, useState } from "react";
import { Check, CircleDot, Search, Sparkles, X } from "lucide-react";
import { DocCubes, type DocPhase } from "@/components/doc-cubes";
import type { Progress } from "@/components/review-provider";
import { cn } from "@/lib/utils";

/**
 * Revue en cours, plein centre : l'amas de cubes, l'étape courante en grand avec le pourcentage animé,
 * trois compteurs, et un fil d'activité qui défile. Les étapes viennent du moteur (SSE) ; les lignes
 * d'activité entre deux étapes sont simulées, plausibles, et se calent sur les vraies données dès qu'elles
 * arrivent (nom du fichier, précédents trouvés).
 */

const CLAUSES = [
  "Identification de la société", "Convocation", "Quorum et feuille de présence", "Ordre du jour", "Rapports préalables",
  "Montant de l'augmentation", "Prix et prime d'émission", "Suppression du DPS", "Modalités de souscription",
  "Délégation au Président", "Modification des statuts", "Résultat des votes", "Pouvoirs pour formalités", "Clôture et signatures",
];
const STATES: ["ok" | "mid" | "ko", string][] = [["ok", "present"], ["mid", "partial"], ["ko", "absent"]];
const ORDER = ["upload", "lecture", "qualification", "grille", "similaires", "correction", "feedback", "fichier"];

type Line = { id: number; icon: "ok" | "mid" | "ko" | "info" | "find" | "spark"; text: string; strong?: string };

function lineFor(step: string, file: string, docs: string[], tick: number): Line | null {
  const pick = <T,>(arr: T[]) => arr[tick % arr.length];
  switch (step) {
    case "upload":
    case "lecture":
      return pick<Line>([
        { id: 0, icon: "info", text: `Opening ${file}` },
        { id: 0, icon: "info", text: "Extracting text layer · stripping training banners" },
        { id: 0, icon: "info", text: "Normalising paragraphs and resolutions" },
      ]);
    case "qualification":
      return pick<Line>([
        { id: 0, icon: "spark", text: "Legal form detected", strong: "SAS" },
        { id: 0, icon: "spark", text: "Nature", strong: "assemblée générale extraordinaire" },
        { id: 0, icon: "spark", text: "Classifying among 13 operation types…" },
        { id: 0, icon: "spark", text: "Operation", strong: "Augmentation de capital en numéraire" },
      ]);
    case "grille": {
      const i = tick % CLAUSES.length;
      const [icon, label] = STATES[(i * 7 + 3) % 3];
      return { id: 0, icon, text: `Clause ${i + 1}/14 · ${CLAUSES[i]}`, strong: label };
    }
    case "similaires":
      if (docs.length && tick % 2 === 1) return { id: 0, icon: "find", text: "Precedent matched", strong: docs[Math.floor(tick / 2) % docs.length] };
      return pick<Line>([
        { id: 0, icon: "find", text: "Scanning 6,410 indexed units…" },
        { id: 0, icon: "find", text: "Ranking 205 acts · same operation → legal form → coverage → recency" },
        { id: 0, icon: "find", text: "Loading the partner's reviews on the top candidates" },
      ]);
    case "correction":
      return pick<Line>([
        { id: 0, icon: "spark", text: "Rewriting", strong: pick(["Convocation", "Quorum et feuille de présence", "Suppression du DPS", "Modalités de souscription", "Résultat des votes"]) },
        { id: 0, icon: "info", text: `Wording taken from ${docs[0] ?? "the closest precedent"} · adapted to the draft's names and figures` },
        { id: 0, icon: "ok", text: "Unknown data kept as", strong: "[à compléter]" },
        { id: 0, icon: "ok", text: "Facts check · dates, amounts, e-mails verified against sources" },
      ]);
    case "feedback":
      return pick<Line>([
        { id: 0, icon: "spark", text: "Writing the partner's feedback…" },
        { id: 0, icon: "spark", text: "Priorities · why it matters in this matter · follow-up questions" },
      ]);
    case "fichier":
      return pick<Line>([
        { id: 0, icon: "ok", text: "Highlighting rewritten passages" },
        { id: 0, icon: "ok", text: "Building the change log with sources" },
        { id: 0, icon: "ok", text: "Scoring the corrected file · saving .docx" },
      ]);
    default:
      return null;
  }
}

/** Compteur qui glisse vers sa cible (ease-out). */
function useCountUp(target: number, ms = 600) {
  const [v, setV] = useState(target);
  const fromRef = useRef(target);
  useEffect(() => {
    const from = fromRef.current, t0 = performance.now();
    let raf = 0;
    const loop = (t: number) => {
      const k = Math.min(1, (t - t0) / ms), e = 1 - Math.pow(1 - k, 3);
      const cur = Math.round(from + (target - from) * e);
      fromRef.current = cur;
      setV(cur);
      if (k < 1) raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return v;
}

const ICON = {
  ok: <Check className="size-3.5 text-success" />,
  mid: <CircleDot className="size-3.5 text-caution" />,
  ko: <X className="size-3.5 text-critical" />,
  info: <span className="block size-1.5 rounded-full bg-muted-foreground/60" />,
  find: <Search className="size-3.5 text-brand" />,
  spark: <Sparkles className="size-3.5 text-brand" />,
};

export function ProgressSteps({ progress, fileName }: { progress: Progress; fileName?: string }) {
  const docs = progress.docs ?? [];
  const file = fileName ?? progress.file ?? "the draft";
  const phase: DocPhase = progress.step === "fichier" ? "imploding" : docs.length > 0 ? "found" : "searching";
  const idx = Math.max(0, ORDER.indexOf(progress.step));

  const [tick, setTick] = useState(0);
  const [lines, setLines] = useState<Line[]>([]);
  const [elapsed, setElapsed] = useState(0);
  const seq = useRef(0);

  const pct = useCountUp(progress.pct, 900);
  const units = useCountUp(idx >= 4 ? 6410 : idx === 3 ? 1800 : 0, 2500);
  const clauses = useCountUp(idx >= 4 ? 14 : idx === 3 ? Math.min(14, 1 + (tick % 14)) : 0, 400);

  useEffect(() => { const t = setInterval(() => setElapsed((s) => s + 1), 1000); return () => clearInterval(t); }, []);
  useEffect(() => { const t = setInterval(() => setTick((k) => k + 1), 850); return () => clearInterval(t); }, []);
  useEffect(() => { setTick(0); }, [progress.step]);
  useEffect(() => {
    const l = lineFor(progress.step, file, docs, tick);
    if (!l) return;
    seq.current += 1;
    const next = { ...l, id: seq.current };
    setLines((prev) => [...prev.slice(-7), next]);
    // Le fil ne dépend que du tick et de l'étape : docs/file sont lus au moment du tick.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tick, progress.step]);

  return (
    <div className="mx-auto flex min-h-[calc(100svh-56px)] w-full max-w-[1100px] flex-col items-center justify-center px-5 pb-40 pt-10">
      <p className="eyebrow">Reviewing · {file}</p>

      <div className="mt-6 scale-[1.15] md:scale-125">
        <DocCubes phase={phase} docs={docs.map((name) => ({ id: name, name }))} size={150} status=" " />
      </div>

      <div className="mt-8 flex flex-wrap items-baseline justify-center gap-x-4 gap-y-1 text-center">
        <span className="font-mono text-[56px] font-medium leading-none tabular-nums text-brand">
          {pct}<span className="text-[28px] text-muted-foreground">%</span>
        </span>
        <h1 className="text-[30px] font-semibold leading-[1.1] md:text-[36px]">{progress.label}…</h1>
      </div>
      <div className="mt-5 h-1.5 w-full max-w-[720px] overflow-hidden rounded-full bg-muted">
        <div className="h-full rounded-full bg-brand transition-[width] duration-700 ease-out" style={{ width: `${progress.pct}%` }} />
      </div>

      <div className="mt-6 grid w-full max-w-[720px] grid-cols-3 gap-px overflow-hidden rounded-md border bg-border">
        {[
          ["units scanned", units.toLocaleString("en")],
          ["clauses checked", `${clauses} / 14`],
          ["precedents found", String(docs.length)],
        ].map(([k, v]) => (
          <div key={k} className="bg-background px-4 py-3">
            <p className="font-mono text-[11px] uppercase tracking-wide text-muted-foreground">{k}</p>
            <p className="mt-1 font-mono text-[22px] tabular-nums">{v}</p>
          </div>
        ))}
      </div>

      <ul className="mt-6 min-h-[200px] w-full max-w-[720px] space-y-1.5 font-mono text-[12.5px]" aria-live="polite">
        {lines.map((l, i) => (
          <li key={l.id}
            className={cn("flex items-center gap-2.5 transition-opacity duration-500", i < lines.length - 3 && "opacity-40")}
            style={{ animation: i === lines.length - 1 ? "fadeUp .35s ease-out" : undefined }}>
            <span className="flex size-4 shrink-0 items-center justify-center">{ICON[l.icon]}</span>
            <span className="text-muted-foreground">{l.text}</span>
            {l.strong && <span className="rounded-sm bg-brand-soft px-1.5 py-0.5 text-foreground">{l.strong}</span>}
          </li>
        ))}
      </ul>

      <p className="mt-4 font-mono text-[11px] text-muted-foreground">{elapsed}s · engine steps are live · activity between steps is illustrative</p>
      <style>{`@keyframes fadeUp { from { opacity: 0; transform: translateY(6px) } to { opacity: 1; transform: none } }`}</style>
    </div>
  );
}
