"use client";

import { useState } from "react";
import { Composer } from "@/components/composer";
import { EmptyState } from "@/components/empty-state";
import { ProgressSteps } from "@/components/progress-steps";
import { ResultView } from "@/components/result-view";
import { TopBar } from "@/components/top-bar";
import { useReview } from "@/components/review-provider";
import type { Exigence } from "@/lib/review";

export default function Page() {
  const { current, reviewing, progress } = useReview();
  const [exigence, setExigence] = useState<Exigence>("standard");
  return (
    <div className="flex min-h-svh flex-col">
      <TopBar />
      <main className="flex-1">
        {reviewing && progress ? <ProgressSteps progress={progress} /> : current ? <ResultView key={current.id} review={current} /> : <EmptyState exigence={exigence} onExigence={setExigence} />}
      </main>
      <Composer exigence={exigence} />
    </div>
  );
}
