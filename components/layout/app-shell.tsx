"use client";

import { MobileNavBar, SideNavBar } from "@/components/layout/side-nav-bar";
import { TopNavBar } from "@/components/layout/top-nav-bar";
import { ChatbotDock } from "@/components/chatbot/chatbot-dock";

type AppShellProps = {
  children: React.ReactNode;
};

export function AppShell({ children }: AppShellProps) {
  return (
    <div className="flex min-h-screen bg-background">
      <SideNavBar />
      <div className="flex min-h-screen flex-1 flex-col">
        <TopNavBar />
        <MobileNavBar />
        <div className="flex min-h-0 flex-1">
          <main className="min-w-0 flex-1 p-6 md:p-8">{children}</main>
          <ChatbotDock />
        </div>
      </div>
    </div>
  );
}
