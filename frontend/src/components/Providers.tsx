"use client";

import { ReactNode } from "react";
import { WebSocketProvider } from "@/context/WebSocketContext";

export function Providers({ children }: { children: ReactNode }) {
  return (
    <WebSocketProvider>
      {children}
    </WebSocketProvider>
  );
}
