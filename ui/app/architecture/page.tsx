import type { Metadata } from "next";
import { SiteHeader } from "@/components/site-header";
import { ArchitectureView } from "./architecture-view";

export const metadata: Metadata = {
  title: "The architecture — thread",
  description: "How Thread goes from a junior's first draft to the firm's standard: structural ingestion, drafting histories, closest precedents, targeted correction, sourced file.",
};

export default function ArchitecturePage() {
  return (
    <div className="min-h-svh bg-background text-foreground">
      <SiteHeader active="/architecture" />
      <ArchitectureView />
    </div>
  );
}
