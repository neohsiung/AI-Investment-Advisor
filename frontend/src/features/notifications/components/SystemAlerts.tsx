import React from "react";
import { useSWRConfig } from "swr";
import TacticalCard from "@/components/ui/TacticalCard";
import { Loader2, Archive } from "lucide-react";
import { NotificationRepository } from "../infra/NotificationRepository";

interface SystemAlertsProps {
  alerts: any[];
  isLoading: boolean;
}

const toast = {
  success: (msg: string) => console.log(`SUCCESS: ${msg}`),
  error: (msg: string) => console.error(`ERROR: ${msg}`),
};

export function SystemAlerts({ alerts, isLoading }: SystemAlertsProps) {
  const { mutate } = useSWRConfig();
  const [isArchiving, setIsArchiving] = React.useState(false);

  const handleArchiveAlerts = async () => {
    // 樂觀更新 (Optimistic UI)
    // 假設成功，先清空 UI 上的通知
    mutate("/api/dashboard/alerts", { status: "success", data: [] }, false);

    try {
      setIsArchiving(true);
      await NotificationRepository.archiveAll();
      toast.success("所有通知已成功封存。");
      // 請求成功後，真正重新驗證 SWR 快取
      mutate("/api/dashboard/alerts");
    } catch (err) {
      toast.error("封存失敗。");
      // 請求失敗時，恢復原本快取
      mutate("/api/dashboard/alerts");
    } finally {
      setIsArchiving(false);
    }
  };

  return (
    <TacticalCard title="系統即時通知" accentColor="var(--tertiary)">
      <div className="space-y-4">
        {isLoading ? (
           <div className="py-12 flex justify-center"><Loader2 className="animate-spin h-6 w-6 text-tertiary" /></div>
        ) : alerts.length > 0 ? (
          alerts.map((alert: any, i: number) => (
            <div key={i} className="p-4 bg-surface-container-low rounded-md border-l-2 border-primary">
              <div className="flex justify-between items-start mb-1">
                <p className="text-[10px] font-label uppercase tracking-widest text-primary font-bold">
                  {alert.type}
                </p>
                <span className="text-[10px] text-on-surface-variant font-mono">{alert.time}</span>
              </div>
              <p className="text-xs text-on-surface leading-snug">{alert.msg}</p>
            </div>
          ))
        ) : (
          <div className="py-12 text-center opacity-20 italic">
            <p className="text-[10px] font-label uppercase tracking-widest">暫無系統事件</p>
          </div>
        )}
      </div>
      <button
        onClick={handleArchiveAlerts}
        disabled={isArchiving || alerts.length === 0}
        className="flex items-center justify-center gap-2 w-full mt-6 py-3 font-label text-[10px] uppercase tracking-[0.2em] text-on-surface-variant hover:text-on-surface transition-all disabled:opacity-20"
      >
        {isArchiving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Archive className="h-3 w-3" />}
        封存所有通知
      </button>
    </TacticalCard>
  );
}
