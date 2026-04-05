import React, { ErrorInfo, ReactNode } from "react";

interface Props {
  fallback: ReactNode;
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    // 更新 state 以致下次渲染時顯示 fallback UI
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    // 可以在這裡將錯誤紀錄到後端監控服務，例如 Sentry
    console.error("Uncaught error in component:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      // 你可以渲染任何自定義的 fallback UI
      return this.props.fallback;
    }

    return this.props.children;
  }
}

// 供頁面使用的 Fallback UI 元件
export function ComponentFallback({ name }: { name: string }) {
  return (
    <div className="p-8 rounded-xl border border-error/20 bg-error/5 flex flex-col items-center justify-center text-center space-y-3">
      <div className="h-10 w-10 rounded-full bg-error/10 flex items-center justify-center">
        <span className="material-symbols-outlined text-error text-xl">error</span>
      </div>
      <div>
        <p className="font-headline font-bold text-on-surface tracking-tight">{name} 模塊暫時無法使用</p>
        <p className="text-[10px] font-label uppercase tracking-widest text-on-surface-variant opacity-60 mt-1">
          系統已自動防護，其餘功能正常
        </p>
      </div>
      <button 
        onClick={() => window.location.reload()}
        className="text-[10px] font-label uppercase tracking-widest text-primary hover:underline"
      >
        嘗試重新載入
      </button>
    </div>
  );
}
