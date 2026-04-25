"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import ThemeToggle from "@/components/ui/ThemeToggle";
import { useAuth } from "@/hooks/useAuth";
import { useDashboardSocket } from "@/hooks/useDashboard";
import { LogOut, User as UserIcon, Bell, Settings, Search, Loader2, Zap, ZapOff, Menu } from "lucide-react";
import { cn } from "@/lib/utils";
import { useSidebar } from "@/context/SidebarContext";

export default function TopBar() {
  const { user, logout, isLoading: authLoading } = useAuth();
  const { stableStatus } = useDashboardSocket();
  const pathname = usePathname();
  const { toggle } = useSidebar();

  const navLinks = [
    { href: "/", label: "總覽" },
    { href: "/performance", label: "績效" },
    { href: "/reports", label: "報告" },
    { href: "/chat", label: "對話" },
    { href: "/data", label: "數據" },
    { href: "/settings", label: "設定" },
  ];

  return (
    <header className="flex justify-between items-center px-4 sm:px-8 h-16 fixed top-0 left-0 lg:left-64 right-0 z-50 bg-background/80 backdrop-blur-md border-b border-outline-variant/10">
      <div className="flex-1 flex items-center gap-4 sm:gap-6 min-w-0">
        {/* Hamburger 按鈕：僅在手機/平板顯示 */}
        <button
          onClick={toggle}
          className="lg:hidden p-2 text-on-surface-variant hover:text-on-surface hover:bg-surface-variant rounded-md transition-all active:scale-95"
          aria-label="Toggle sidebar"
        >
          <Menu className="h-5 w-5" />
        </button>

        <nav className="hidden sm:flex items-center gap-4 lg:gap-6 min-w-0 overflow-hidden">
          {navLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={cn(
                "transition-all duration-200 px-2 py-1 rounded font-headline font-bold tracking-tight text-sm",
                pathname === link.href
                  ? "text-primary border-b-2 border-primary-container"
                  : "text-on-surface-variant hover:text-on-surface hover:bg-surface-variant"
              )}
            >
              {link.label}
            </Link>
          ))}
        </nav>
      </div>

      <div className="flex items-center gap-2 sm:gap-4 ml-4 flex-shrink-0">
        <div className="relative group hidden sm:block">
          <input
            type="text"
            placeholder="Search parameters..."
            className="bg-surface-container-low border-none text-on-surface text-xs font-label uppercase tracking-wider rounded-md pl-10 pr-4 py-2 w-32 sm:w-48 lg:w-64 focus:ring-1 focus:ring-primary-container transition-all"
          />
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant h-4 w-4" />
        </div>

        <div className="flex items-center gap-1 sm:gap-2">
          <ThemeToggle />

          <button className="p-2 text-on-surface-variant hover:bg-surface-variant rounded-full transition-all active:scale-95 group">
            <Bell className="h-5 w-5 group-hover:text-primary transition-colors" />
          </button>

          <button className="hidden sm:flex p-2 text-on-surface-variant hover:bg-surface-variant rounded-full transition-all active:scale-95 group">
            <Settings className="h-5 w-5 group-hover:text-primary transition-colors" />
          </button>

          <div className="hidden sm:block h-4 w-px bg-outline-variant/20 mx-1" />

          {/* WebSocket Status Indicator - only show when authenticated */}
          {user && (
            <div className="hidden sm:flex items-center gap-1.5 px-2 py-1 rounded-md bg-surface-container-highest/50 border border-outline-variant/10">
              {stableStatus === "LIVE" ? (
                <>
                  <Zap className="h-3 w-3 text-secondary fill-secondary animate-pulse" />
                  <span className="text-[9px] font-black uppercase text-secondary tracking-widest">Live</span>
                </>
              ) : (
                <>
                  <ZapOff className="h-3 w-3 text-on-surface-variant/40" />
                  <span className="text-[9px] font-black uppercase text-on-surface-variant/40 tracking-widest">Polling</span>
                </>
              )}
            </div>
          )}

          <div className="flex items-center gap-2 sm:gap-3 ml-1 sm:ml-4 bg-surface-container-high px-2 sm:px-3 py-1.5 rounded-full border border-outline-variant/10 group">
            {authLoading ? (
              <Loader2 className="h-4 w-4 animate-spin text-primary" />
            ) : user ? (
              <>
                <div className="hidden sm:flex flex-col items-end">
                  <span className="text-[10px] font-bold text-on-surface tracking-tight truncate max-w-[120px]">
                    {user.email}
                  </span>
                  <span className="text-[8px] font-black uppercase text-secondary tracking-widest">Architect</span>
                </div>
                <button
                  onClick={logout}
                  className="p-1.5 text-on-surface-variant hover:text-error hover:bg-error/10 rounded-full transition-all"
                  title="Secure Logout"
                >
                  <LogOut className="h-4 w-4" />
                </button>
              </>
            ) : (
              <Link href="/auth/login" className="flex items-center gap-2">
                <UserIcon className="h-4 w-4 text-primary" />
                <span className="text-xs font-bold uppercase tracking-widest">Sign In</span>
              </Link>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
