"use client";

import { Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useReview } from "@/components/review-provider";

export function TopBar() {
  const { current, reviewing, progress } = useReview();
  const title = reviewing ? `Reviewing… ${progress?.pct ?? 0}%` : current ? `${current.dossier} · ${current.qualification.categorie_libelle || current.type_operation}` : "New workspace";
  return (
    <header className="flex h-14 items-center justify-between border-b px-5">
      <nav className="flex items-center gap-2 text-[13px]" aria-label="Breadcrumb">
        <span className="text-muted-foreground">Workspace</span>
        <span className="text-muted-foreground">/</span>
        <span className="truncate">{title}</span>
      </nav>
      {current && !reviewing && (
        <Button variant="outline" size="sm" className="h-9 rounded-lg bg-background px-3 font-normal shadow-none" nativeButton={false} render={<a href={current.docx_url} download />}>
          <Download className="size-4" /> Corrected .docx
        </Button>
      )}
    </header>
  );
}
