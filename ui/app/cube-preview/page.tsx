"use client";

import { useEffect, useState } from "react";
import { DocCubes, foundDurationMs, type DocPhase, type FoundDoc } from "@/components/doc-cubes";

/** Aperçu temporaire de l'animation « documents trouvés » (à supprimer). Données d'exemple tirées du corpus. */
const DOCS: FoundDoc[] = [
  {
    id: "ab-17-06", name: "ALICE & BOB – Actes du 17-06-2025",
    threads: [
      { label: "Final (PDF)", href: "#" }, { label: "V2", href: "#" }, { label: "V1", href: "#" },
      { label: "Revue V1 – A. Berthier", href: "#" }, { label: "Revue V2 – A. Berthier", href: "#" }, { label: "Validation", href: "#" },
    ],
  },
  { id: "ynsect", name: "YNSECT – Actes du 15-04-2025" },
  { id: "gravithy", name: "GRAVITHY – Actes du 14-05-2025" },
];

export default function Page() {
  const [phase, setPhase] = useState<DocPhase>("searching");
  const [run, setRun] = useState(0);

  useEffect(() => {
    setPhase("searching");
    const t1 = setTimeout(() => setPhase("found"), 1600);
    const t2 = setTimeout(() => setPhase("imploding"), 1600 + foundDurationMs(DOCS.length) + 600);
    const t3 = setTimeout(() => setPhase("done"), 1600 + foundDurationMs(DOCS.length) + 600 + 900);
    return () => [t1, t2, t3].forEach(clearTimeout);
  }, [run]);

  return (
    <div className="flex min-h-svh flex-col items-center justify-center gap-6 bg-background p-10">
      <div className="w-full max-w-[900px] rounded-xl border bg-background p-4">
        <DocCubes phase={phase} docs={DOCS} />
      </div>
      <button type="button" className="font-mono text-[12px] text-muted-foreground underline" onClick={() => setRun((r) => r + 1)}>
        replay ({phase})
      </button>
    </div>
  );
}
