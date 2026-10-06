import { Suspense } from "react";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/app-sidebar";
import { ReviewProvider } from "@/components/review-provider";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={null}>
      <ReviewProvider>
        <SidebarProvider style={{ "--sidebar-width": "300px" } as React.CSSProperties}>
          <AppSidebar />
          <SidebarInset className="bg-background">{children}</SidebarInset>
        </SidebarProvider>
      </ReviewProvider>
    </Suspense>
  );
}
