"use client";

import { Globe, ShieldCheck, Zap, Globe as GlobeIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export default function LoginPage() {
  // Use relative URL - Next.js proxy rewrites /api/* to http://mcp_server:8000/api/*
  // This ensures it works in Docker, local dev, and production.
  const BACKEND_LOGIN_URL = "/api/auth/login";

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-surface-container-lowest text-on-surface p-6">
      {/* 背景裝飾 */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-primary/5 blur-3xl rounded-full" />
        <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-secondary/5 blur-3xl rounded-full" />
      </div>

      <div className="relative max-w-md w-full bg-surface-container-low border border-outline-variant p-10 rounded-3xl shadow-2xl backdrop-blur-xl">
        <div className="text-center mb-10">
          <div className="inline-flex items-center justify-center p-3 mb-6 rounded-2xl bg-primary/10 border border-primary/20">
            <ShieldCheck className="h-10 w-10 text-primary" />
          </div>
          <h1 className="text-3xl font-black tracking-tighter mb-2 font-space uppercase">
            Quant Intelligence
          </h1>
          <p className="text-secondary font-medium tracking-tight">
            Authorize access to the neural investment interface.
          </p>
        </div>

        <div className="space-y-6">
          <a
            href={BACKEND_LOGIN_URL}
            className={cn(
              "flex items-center justify-center gap-3 w-full py-4 px-6 rounded-2xl",
              "bg-primary text-on-primary hover:bg-primary/90 transition-all font-bold shadow-lg shadow-primary/20",
              "transform hover:scale-[1.02] active:scale-[0.98]"
            )}
          >
            <Globe className="h-5 w-5 fill-current text-white" />
            Continue with Google
          </a>

          <div className="grid grid-cols-2 gap-4 pt-6 mt-8 border-t border-outline-variant">
             <div className="flex items-center gap-2 text-xs font-bold text-secondary uppercase tracking-widest">
               <Zap className="h-3 w-3" /> Ultra Low Latency
             </div>
             <div className="flex items-center gap-2 text-xs font-bold text-secondary uppercase tracking-widest">
               <Globe className="h-3 w-3" /> Global Alpha Mesh
             </div>
          </div>
        </div>

        {/* 戰術編號 */}
        <div className="absolute -bottom-1 -right-1 text-[120px] font-black text-on-surface/5 select-none pointer-events-none">
           00
        </div>
      </div>
      
      <p className="mt-12 text-xs font-bold text-outline-variant uppercase tracking-[0.2em]">
        Quantum Sentinel Deployment Interface v1.1.0
      </p>
    </div>
  );
}
