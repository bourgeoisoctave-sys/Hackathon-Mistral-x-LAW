"use client";

import { createContext, useCallback, useContext, useMemo, useState } from "react";
import type { Exigence, Review } from "@/lib/review";
import demo from "@/data/demo/helianthe_v1.json";

export interface Progress { step: string; label: string; pct: number; startedAt: number; docs?: string[]; file?: string }

interface ReviewState {
  reviews: Review[];
  current: Review | null;
  select: (id: string | null) => void;
  newWorkspace: () => void;
  importDraft: (file: File, exigence: Exigence) => Promise<void>;
  loadDemo: () => void;
  reviewing: boolean;
  progress: Progress | null;
  error: string | null;
  clearError: () => void;
}

const Ctx = createContext<ReviewState | null>(null);
const DEMO = demo as unknown as Review;

export function ReviewProvider({ children }: { children: React.ReactNode }) {
  const [reviews, setReviews] = useState<Review[]>([]);
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [reviewing, setReviewing] = useState(false);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [error, setError] = useState<string | null>(null);

  const current = reviews.find((r) => r.id === currentId) ?? null;

  const importDraft = useCallback(async (file: File, exigence: Exigence) => {
    setReviewing(true);
    setError(null);
    const startedAt = Date.now();
    setProgress({ step: "upload", label: "Uploading the draft", pct: 2, startedAt, file: file.name });
    const form = new FormData();
    form.set("file", file);
    form.set("exigence", exigence);
    form.set("dossier", "helianthe");
    try {
      const res = await fetch("/api/review", { method: "POST", body: form });
      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      let result: Review | null = null;
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const frames = buf.split("\n\n");
        buf = frames.pop() ?? "";
        for (const frame of frames) {
          const ev = /^event: (.+)$/m.exec(frame)?.[1];
          const data = /^data: (.+)$/m.exec(frame)?.[1];
          if (!ev || !data) continue;
          const payload = JSON.parse(data);
          if (ev === "step") setProgress((p) => ({ ...payload, docs: payload.docs ?? p?.docs, file: p?.file, startedAt }));
          else if (ev === "result") result = payload as Review;
          else if (ev === "error") throw new Error(payload.detail ? `${payload.error}\n${payload.detail}` : payload.error);
        }
      }
      if (!result) throw new Error("Le moteur n'a renvoyé aucun résultat.");
      const done = result;
      setReviews((rs) => [...rs, done]);
      setCurrentId(done.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setReviewing(false);
      setProgress(null);
    }
  }, []);

  const loadDemo = useCallback(() => {
    setReviews((rs) => (rs.some((r) => r.id === DEMO.id) ? rs : [...rs, DEMO]));
    setCurrentId(DEMO.id);
    setError(null);
  }, []);

  const value = useMemo<ReviewState>(() => ({
    reviews, current, select: setCurrentId, newWorkspace: () => { setCurrentId(null); setError(null); },
    importDraft, loadDemo, reviewing, progress, error, clearError: () => setError(null),
  }), [reviews, current, importDraft, loadDemo, reviewing, progress, error]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useReview(): ReviewState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useReview() hors de <ReviewProvider>");
  return v;
}
