"use client";

import Image from "next/image";
import Link from "next/link";
import { FileText, HelpCircle, PanelLeft, Plus, Sparkles } from "lucide-react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  Sidebar, SidebarContent, SidebarFooter, SidebarGroup, SidebarGroupLabel, SidebarHeader,
  SidebarMenu, SidebarMenuButton, SidebarMenuItem, useSidebar,
} from "@/components/ui/sidebar";
import { cn } from "@/lib/utils";
import { scoreTone, TONE_CLASSES } from "@/lib/review";
import { useReview } from "@/components/review-provider";

export function AppSidebar() {
  const { toggleSidebar } = useSidebar();
  const { reviews, current, select, newWorkspace, loadDemo, reviewing } = useReview();
  const corpus = reviews[0]?.corpus;

  return (
    <Sidebar className="border-r border-sidebar-border">
      <SidebarHeader className="gap-3 px-3 pt-3">
        <div className="flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2" aria-label="thread — home">
            <Image src="/thread-mark.svg" alt="" width={24} height={23} className="size-6" />
            <span className="text-[18px] font-bold leading-none tracking-tight text-brand">thread</span>
          </Link>
          <Button variant="ghost" size="icon" className="size-8 rounded-lg text-muted-foreground" aria-label="Collapse sidebar" onClick={toggleSidebar}>
            <PanelLeft className="size-4" />
          </Button>
        </div>
        <Button variant="outline" className="h-10 w-full justify-start gap-2 rounded-lg bg-background font-normal shadow-none" onClick={newWorkspace} disabled={reviewing}>
          <Plus className="size-4" /> New workspace
        </Button>
      </SidebarHeader>

      <SidebarContent className="px-1">
        <SidebarGroup>
          <SidebarGroupLabel className="eyebrow px-3">Reviews</SidebarGroupLabel>
          <SidebarMenu>
            {reviews.length === 0 && (
              <p className="px-3 py-2 text-[13px] text-muted-foreground">No review yet. Import a draft to start.</p>
            )}
            {reviews.map((r) => {
              const active = current?.id === r.id;
              const before = scoreTone(r.score.final).tone;
              const after = scoreTone(r.score_apres.final).tone;
              return (
                <SidebarMenuItem key={r.id}>
                  <SidebarMenuButton isActive={active} onClick={() => select(r.id)}
                    className="h-auto flex-col items-start gap-0.5 rounded-lg px-3 py-2 data-[active=true]:bg-sidebar-accent">
                    <span className="flex w-full items-center gap-2 text-[14px]">
                      <FileText className="size-4 shrink-0 text-muted-foreground" />
                      <span className="flex-1 truncate font-medium">{r.dossier}</span>
                      {!r.live && <span className="rounded-sm bg-muted px-1 font-mono text-[10px] text-muted-foreground">demo</span>}
                    </span>
                    <span className="flex w-full items-center gap-2 pl-6 font-mono text-[11px] text-muted-foreground">
                      <span className="truncate">{r.qualification.categorie_libelle || r.type_operation}</span>
                      <span className="ml-auto shrink-0 tabular-nums">
                        <span className={TONE_CLASSES[before].text}>{r.score.final}</span> → <span className={TONE_CLASSES[after].text}>{r.score_apres.final}</span>
                      </span>
                    </span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              );
            })}
            {!reviews.some((r) => !r.live) && (
              <SidebarMenuItem>
                <SidebarMenuButton onClick={loadDemo} className="h-9 rounded-lg px-3 text-[14px] text-muted-foreground" disabled={reviewing}>
                  <Sparkles className="size-4" /> Load the demo review
                </SidebarMenuButton>
              </SidebarMenuItem>
            )}
          </SidebarMenu>
        </SidebarGroup>

        <SidebarGroup>
          <SidebarGroupLabel className="eyebrow px-3">Firm corpus</SidebarGroupLabel>
          <div className={cn("px-3 font-mono text-[12px] leading-6 text-muted-foreground", !corpus && "opacity-60")}>
            <div>{corpus?.actes ?? 200} acts (greffe)</div>
            <div>129 drafting histories</div>
            <div>{corpus?.revues ?? 645} partner review emails</div>
            <div>{corpus?.templates ?? 5} PV templates</div>
            <div>{(corpus?.chunks ?? 6410).toLocaleString("en")} indexed units</div>
          </div>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter className="px-3 pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Avatar className="size-6"><AvatarFallback className="bg-foreground text-[11px] text-background">L</AvatarFallback></Avatar>
            <span className="text-[14px]">Léa Marchand</span>
            <span className="font-mono text-[11px] text-muted-foreground">junior</span>
          </div>
          <Button variant="ghost" size="icon" className="size-8 rounded-lg text-muted-foreground" aria-label="Help"><HelpCircle className="size-4" /></Button>
        </div>
      </SidebarFooter>
    </Sidebar>
  );
}
