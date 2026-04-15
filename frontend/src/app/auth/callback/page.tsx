"use client";

import { useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";

function TokenCollector() {
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    const accessToken = searchParams.get("access_token");
    const refreshToken = searchParams.get("refresh_token");

    if (accessToken && refreshToken) {
      // 1. 持久化 Tokens 至 localStorage (Sprint 3 採用機制)
      localStorage.setItem("access_token", accessToken);
      localStorage.setItem("refresh_token", refreshToken);

      // 2. 成功後引導至 CommandCenter
      router.push("/");
    } else {
      // 3. 異常處理：若遺失 Token 則回歸登入頁
      console.error("Auth Callback: Missing tokens in URL");
      router.push("/auth/login?error=InvalidSession");
    }
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
