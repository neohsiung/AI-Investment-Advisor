"use client";

import { useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { mutate } from "swr";
import { Loader2 } from "lucide-react";

function TokenCollector() {
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    // 2026-07-12: the real tokens no longer travel in this URL — only a
    // short-lived, single-use opaque exchange code does. We POST it to
    // /auth/exchange to get the actual tokens back in the response body,
    // then persist to localStorage exactly as before (unchanged for every
    // downstream consumer: WebSocketContext, chat page, api.ts).
    const code = searchParams.get("code");
    if (!code) {
      console.error("Auth Callback: Missing exchange code in URL");
      router.push("/auth/login?error=InvalidSession");
      return;
    }

    fetch("/api/v1/auth/exchange", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code }),
    })
      .then((res) => {
        if (!res.ok) throw new Error(`exchange failed: ${res.status}`);
        return res.json();
      })
      .then(({ access_token, refresh_token }) => {
        localStorage.setItem("access_token", access_token);
        localStorage.setItem("refresh_token", refresh_token);
        return mutate("/api/v1/auth/me");
      })
      .then(() => router.push("/"))
      .catch((err) => {
        console.error("Auth Callback: exchange failed", err);
        router.push("/auth/login?error=InvalidSession");
      });
  }, [searchParams, router]);

  return (
    <div className="flex flex-col items-center justify-center min-h-screen space-y-4 bg-background">
      <Loader2 className="h-12 w-12 text-primary animate-spin" />
      <p className="text-muted-foreground animate-pulse font-mono tracking-widest text-sm">
        ESTABLISHING SECURE SESSION...
      </p>
    </div>
  );
}

export default function AuthCallbackPage() {
  return (
    <Suspense fallback={
      <div className="flex items-center justify-center min-h-screen">
        <Loader2 className="h-12 w-12 text-primary animate-spin" />
      </div>
    }>
      <TokenCollector />
    </Suspense>
  );
}
