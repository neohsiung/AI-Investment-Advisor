"use client";

import React from "react";
import { usePathname } from "next/navigation";
import Sidebar from "./Sidebar";
import TopBar from "./TopBar";
import SidebarOverlay from "./SidebarOverlay";

interface AppShellProps {
  children: React.ReactNode;
}

export default function AppShell({ children }: AppShellProps) {
  const pathname = usePathname();
  const isAuthPage = pathname?.startsWith("/auth");

  if (isAuthPage) {
    return (
      <main className="flex-1 min-h-screen bg-background">
        {children}
      </main>
    );
  }

  return (
    <div className="min-h-full flex font-body bg-background text-on-surface w-full">
      <Sidebar />
      <SidebarOverlay />
      <div className="flex-1 flex flex-col min-h-screen ml-0 lg:ml-64 transition-all duration-300">
        <TopBar />
        <main className="flex-1 flex flex-col min-h-0 relative">
          {children}
        </main>
      </div>
    </div>
  );
}
