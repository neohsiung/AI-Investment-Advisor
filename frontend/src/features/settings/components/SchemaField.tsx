"use client";

import React from "react";
import { Eye, EyeOff, AlertTriangle, RotateCw } from "lucide-react";
import { cn } from "@/lib/utils";
import type { SettingsField } from "../types";

interface Props {
  field: SettingsField;
  value: unknown;
  onChange: (key: string, value: unknown) => void;
  error?: string;
  dirty?: boolean;
}

/**
 * Renders one field from the registry.
 *
 * One component per *type*, not per key — which is the whole point. The page
 * this replaced had a hand-written JSX block for every individual setting, so
 * adding a knob meant editing TypeScript; now it means adding a YAML row.
 *
 * 依「型別」而非「鍵」渲染：新增設定改 YAML 即可，不需動 TypeScript。
 */
export function SchemaField({ field, value, onChange, error, dirty }: Props) {
  const [reveal, setReveal] = React.useState(false);

  const label = field.label_zh || field.label_en;
  const help = field.help_zh || field.help_en;

  const inputBase = cn(
    "w-full rounded-md border bg-surface-container px-3 py-2 text-sm transition-colors",
    "focus:outline-none focus:ring-1 focus:ring-primary",
    error ? "border-error" : "border-outline-variant/30",
  );

  function render() {
    switch (field.type) {
      case "bool":
        return (
          <button
            type="button"
            role="switch"
            aria-checked={value === true}
            onClick={() => onChange(field.key, !(value === true))}
            className={cn(
              "relative h-6 w-11 rounded-full transition-colors",
              value === true ? "bg-primary" : "bg-outline-variant/40",
            )}
          >
            <span
              className={cn(
                "absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform",
                value === true ? "translate-x-5" : "translate-x-0.5",
              )}
            />
          </button>
        );

      case "enum":
        return (
          <select
            className={inputBase}
            value={String(value ?? "")}
            onChange={(e) => onChange(field.key, e.target.value)}
          >
            <option value="">—</option>
            {(field.enum ?? []).map((opt) => (
              <option key={String(opt)} value={String(opt)}>{String(opt)}</option>
            ))}
          </select>
        );

      case "secret":
        return (
          <div className="relative">
            <input
              type={reveal ? "text" : "password"}
              className={cn(inputBase, "pr-10")}
              // Secrets are never sent to the browser. An empty box with a
              // "configured" placeholder means "a value exists, server-side";
              // typing replaces it, leaving it alone keeps it.
              // secret 不會傳到瀏覽器；留空代表沿用既有值。
              placeholder={field.has_value ? "•••••••• (已設定，留空則不變)" : "未設定"}
              value={String(value ?? "")}
              onChange={(e) => onChange(field.key, e.target.value)}
            />
            <button
              type="button"
              onClick={() => setReveal((r) => !r)}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-on-surface-variant"
              aria-label={reveal ? "Hide" : "Show"}
            >
              {reveal ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
        );

      case "int":
      case "float":
        return (
          <input
            type="number"
            className={inputBase}
            step={field.type === "float" ? "any" : 1}
            min={field.min ?? undefined}
            max={field.max ?? undefined}
            value={value === null || value === undefined ? "" : String(value)}
            onChange={(e) =>
              onChange(field.key, e.target.value === "" ? null : Number(e.target.value))
            }
          />
        );

      case "json":
      case "list":
        return (
          <textarea
            className={cn(inputBase, "font-mono text-xs min-h-[76px]")}
            value={
              typeof value === "string"
                ? value
                : JSON.stringify(value ?? (field.type === "list" ? [] : {}), null, 2)
            }
            onChange={(e) => onChange(field.key, e.target.value)}
          />
        );

      case "time":
        return (
          <input
            type="time"
            className={inputBase}
            value={String(value ?? "")}
            onChange={(e) => onChange(field.key, e.target.value)}
          />
        );

      default:
        return (
          <input
            type="text"
            className={inputBase}
            value={String(value ?? "")}
            onChange={(e) => onChange(field.key, e.target.value)}
          />
        );
    }
  }

  return (
    <div className="py-3 border-b border-outline-variant/10 last:border-0">
      <div className="flex items-start justify-between gap-6">
        <div className="min-w-0 flex-1">
          <label className="flex items-center gap-2 text-sm font-medium text-on-surface">
            {label}
            {dirty && <span className="h-1.5 w-1.5 rounded-full bg-primary" title="未儲存" />}
            {field.danger && (
              <span
                className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-error bg-error/10"
                title="影響真實資金"
              >
                <AlertTriangle className="h-3 w-3" /> 資金
              </span>
            )}
            {field.restart && (
              <span
                className="inline-flex items-center gap-1 text-[10px] uppercase tracking-wide text-on-surface-variant"
                title="需重啟容器才生效"
              >
                <RotateCw className="h-3 w-3" /> 重啟
              </span>
            )}
          </label>
          <p className="mt-0.5 font-mono text-[10px] text-on-surface-variant/70">{field.key}</p>
          {help && <p className="mt-1 text-xs text-on-surface-variant">{help}</p>}
          {error && <p className="mt-1 text-xs text-error">{error}</p>}
        </div>
        <div className="w-64 shrink-0">{render()}</div>
      </div>
    </div>
  );
}
