"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { X } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { useSidebar } from "@/context/SidebarContext";

const navItems = [
  { id: "command", label: "Command Center", icon: "terminal", href: "/" },
  { id: "performance", label: "績效分析", icon: "monitoring", href: "/performance" },
  { id: "reports", label: "報告", icon: "description", href: "/reports" },
  { id: "chat", label: "AI 對話", icon: "smart_toy", href: "/chat" },
  { id: "data", label: "數據", icon: "table_chart", href: "/data" },
  { id: "intelligence", label: "市場情報", icon: "crisis_alert", href: "/intelligence" },
  { id: "universe", label: "標的池", icon: "layers", href: "/universe" },
  { id: "settings", label: "Settings", icon: "tune", href: "/settings" },
];

export default function Sidebar() {
  const pathname = usePathname();
  const { logout } = useAuth();
  const { isOpen, close } = useSidebar();

  return (
    <aside
      className={`
        fixed inset-y-0 left-0 z-50 w-64
        bg-surface-container-low border-r border-outline-variant/15
        flex flex-col shadow-[20px_0_40px_rgba(0,0,0,0.4)]
        transform transition-transform duration-300
        ${isOpen ? "translate-x-0" : "-translate-x-full"}
        lg:translate-x-0 lg:static lg:inset-auto
      `}
    >
      <div className="p-6 flex items-center gap-3">
        <div className="w-8 h-8 bg-gradient-to-br from-primary-container to-primary rounded-md flex items-center justify-center">
          <span className="material-symbols-outlined text-on-primary text-xl" style={{ fontVariationSettings: "'FILL' 1" }}>
            deployed_code
          </span>
        </div>
        <div className="flex-1">
          <h2 className="text-lg font-bold text-primary font-headline tracking-tighter uppercase">QUANTUM AI</h2>
          <p className="font-label text-[10px] uppercase tracking-widest text-on-surface-variant opacity-70">V3.2 Active</p>
        </div>
        {/* 手機版關閉按鈕 */}
        <button
          onClick={close}
          className="lg:hidden p-1.5 text-on-surface-variant hover:text-on-surface hover:bg-surface-variant rounded-md transition-all"
          aria-label="Close sidebar"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      <nav className="flex-1 mt-4 px-2 space-y-1">
        {navItems.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.id}
              href={item.href}
              onClick={close}
              className={`flex items-center gap-3 px-4 py-3 rounded-md transition-all active:translate-x-1 duration-150 group ${isActive
                  ? "bg-gradient-to-r from-primary-container to-primary text-white shadow-md"
                  : "text-on-surface-variant hover:text-on-surface hover:bg-surface-variant"
                }`}
            >
              <span
                className="material-symbols-outlined"
                style={{ fontVariationSettings: isActive ? "'FILL' 1" : "'FILL' 0" }}
              >
                {item.icon}
              </span>
              <span className="font-label text-sm uppercase tracking-widest">{item.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="px-4 pb-8 space-y-6">
        <button className="w-full py-3 bg-surface-container-highest hover:bg-surface-bright text-primary font-label text-xs uppercase tracking-widest rounded-md border border-outline-variant/20 transition-all active:scale-95">
          Deploy New Agent
        </button>

        <div className="pt-6 border-t border-outline-variant/10 space-y-2">
          <div className="flex items-center gap-3 px-2 py-2 text-on-surface-variant hover:text-on-surface cursor-pointer transition-all hover:bg-surface-variant rounded-md">
            <span className="material-symbols-outlined text-sm">help_outline</span>
            <span className="font-label text-xs uppercase tracking-widest">Help</span>
          </div>
          <div
            onClick={logout}
            className="flex items-center gap-3 px-2 py-2 text-error hover:opacity-80 cursor-pointer transition-all hover:bg-error-container/10 rounded-md"
          >
            <span className="material-symbols-outlined text-sm">logout</span>
            <span className="font-label text-xs uppercase tracking-widest">Logout</span>
          </div>
        </div>
      </div>
    </aside>
  );
}
