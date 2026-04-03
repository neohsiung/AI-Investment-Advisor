"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const navItems = [
  { id: "command", label: "Command Center", icon: "terminal", href: "/" },
  { id: "agents", label: "Agent Status", icon: "memory", href: "/agents" },
  { id: "market", label: "Market Analysis", icon: "monitoring", href: "/market" },
  { id: "risk", label: "Risk Profile", icon: "security", href: "/risk" },
  { id: "settings", label: "Settings", icon: "tune", href: "/settings" },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed left-0 top-0 h-full w-64 bg-surface-container-low border-r border-outline-variant/15 flex flex-col shadow-[20px_0_40px_rgba(0,0,0,0.4)] z-[60]">
      <div className="p-6 flex items-center gap-3">
        <div className="w-8 h-8 bg-gradient-to-br from-primary-container to-primary rounded-md flex items-center justify-center">
          <span className="material-symbols-outlined text-on-primary text-xl" style={{ fontVariationSettings: "'FILL' 1" }}>
            deployed_code
          </span>
        </div>
        <div>
          <h2 className="text-lg font-bold text-primary font-headline tracking-tighter uppercase">QUANTUM AI</h2>
          <p className="font-label text-[10px] uppercase tracking-widest text-on-surface-variant opacity-70">V3.2 Active</p>
        </div>
      </div>

      <nav className="flex-1 mt-4 px-2 space-y-1">
        {navItems.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.id}
              href={item.href}
              className={`flex items-center gap-3 px-4 py-3 rounded-md transition-all active:translate-x-1 duration-150 group ${
                isActive
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
          <div className="flex items-center gap-3 px-2 py-2 text-error hover:opacity-80 cursor-pointer transition-all hover:bg-error-container/10 rounded-md">
            <span className="material-symbols-outlined text-sm">logout</span>
            <span className="font-label text-xs uppercase tracking-widest">Logout</span>
          </div>
        </div>
      </div>
    </aside>
  );
}
