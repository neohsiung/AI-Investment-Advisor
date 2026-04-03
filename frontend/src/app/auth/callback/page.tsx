"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";

export default function AuthCallbackPage() {
  const router = useRouter();

  useEffect(() => {
    // 成功登入後，後端已設置 HTTPOnly Cookies
    // 我們只需等待組件掛載並重定向回首頁即可
    // 真實環境可以呼叫一個 /api/auth/me 來確認狀態
    const timer = setTimeout(() => {
      router.push("/");
    }, 1500);

    return () => clearTimeout(timer);
  }, [router]);

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-surface-container-lowest text-on-surface">
      <div className="relative flex flex-col items-center">
        {/* 指令傳輸動畫 */}
        <div className="mb-8 relative">
           <Loader2 className="h-12 w-12 text-primary animate-spin" />
           <div className="absolute inset-0 bg-primary/20 blur-xl animate-pulse rounded-full" />
        </div>
        
        <h1 className="text-2xl font-bold tracking-tighter sm:text-3xl mb-2 font-space">
          SYNCHRONIZING SECURE TUNNEL
        </h1>
        <p className="text-secondary font-medium animate-pulse">
          Establishing encrypted connection to Archon Matrix...
        </p>
        
        {/* 戰術裝飾線 */}
        <div className="mt-12 h-px w-48 bg-gradient-to-r from-transparent via-primary/50 to-transparent" />
      </div>
    </div>
  );
}
