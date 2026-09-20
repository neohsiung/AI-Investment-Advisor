"use client";

import React from "react";
import { mutate } from "swr";
import { Loader2, Save, CheckCircle2, AlertCircle } from "lucide-react";
import api from "@/lib/api";
import { cn } from "@/lib/utils";
import { useSettingsSchema } from "../useSettingsSchema";
import { SchemaField } from "./SchemaField";
import type { SettingsField } from "../types";

/**
 * The whole settings form, rendered from the server-side registry.
 *
 * Two behaviours worth stating, because the page this replaced got both wrong:
 *
 * 1. It submits ONLY changed keys. The old page POSTed the entire GET /settings
 *    payload back, which by now includes 53 machine-written `alpha_spy_*` rows
 *    of generated code and other non-configuration state. With the server
 *    validating against the registry, that would be rejected wholesale — and
 *    round-tripping generated code through a settings form was never right.
 *
 * 2. An untouched secret is never submitted, so leaving the box empty keeps the
 *    stored credential instead of overwriting it with "".
 *
 * 只送出有變更的鍵：舊頁面會把整份 GET /settings 回傳（含 53 列機器寫入的
 * 產生程式碼）原樣送回。未修改的 secret 不送出，留空即沿用既有值。
 */
export interface SchemaFormProps {
  allowedGroupIds?: string[];
  initialGroup?: string;
  hideGroupTabs?: boolean;
}

export function SchemaForm({
  allowedGroupIds,
  initialGroup,
  hideGroupTabs = false,
}: SchemaFormProps = {}) {
  const { groups: allGroups, values, isLoading, error } = useSettingsSchema();

  const groups = React.useMemo(() => {
    if (!allowedGroupIds || allowedGroupIds.length === 0) return allGroups;
    return allGroups.filter((g) => allowedGroupIds.includes(g.id));
  }, [allGroups, allowedGroupIds]);

  const [active, setActive] = React.useState<string>(initialGroup || "");
  const [edits, setEdits] = React.useState<Record<string, unknown>>({});
  const [fieldErrors, setFieldErrors] = React.useState<Record<string, string>>({});
  const [banner, setBanner] = React.useState<{ kind: "ok" | "err"; msg: string } | null>(null);
  const [saving, setSaving] = React.useState(false);

  React.useEffect(() => {
    if (!active && groups.length) {
      setActive(initialGroup && groups.some((g) => g.id === initialGroup) ? initialGroup : groups[0].id);
    }
  }, [groups, active, initialGroup]);

  const dirtyCount = Object.keys(edits).length;

  const valueOf = (f: SettingsField) =>
    f.key in edits ? edits[f.key] : f.secret ? "" : values[f.key] ?? f.default;

  const onChange = (key: string, value: unknown) => {
    setEdits((prev) => ({ ...prev, [key]: value }));
    setFieldErrors((prev) => {
      if (!(key in prev)) return prev;
      const next = { ...prev };
      delete next[key];
      return next;
    });
  };

  async function save() {
    setSaving(true);
    setBanner(null);
    setFieldErrors({});

    // Drop untouched secrets: an empty string would clear a stored credential.
    // 空字串會清掉已儲存的憑證，故未輸入的 secret 不送出。
    const payload: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(edits)) {
      const field = groups.flatMap((g) => g.fields).find((f) => f.key === k);
      if (field?.secret && (v === "" || v === null)) continue;
      payload[k] = v;
    }

    if (Object.keys(payload).length === 0) {
      setBanner({ kind: "ok", msg: "沒有變更需要儲存。" });
      setSaving(false);
      return;
    }

    try {
      await api.post("/api/v1/settings", { settings: payload });
      setBanner({ kind: "ok", msg: `已儲存 ${Object.keys(payload).length} 項設定。` });
      setEdits({});
      mutate("/api/v1/settings");
      mutate("/api/v1/settings/schema");
    } catch (err: any) {
      // The server returns 400 with per-field detail for validation failures
      // (schema-derived text, safe to display) and an opaque 500 otherwise.
      // 驗證失敗回 400 並帶欄位層級訊息；其他失敗回不透明的 500。
      const detail: string = err?.response?.data?.detail ?? "儲存失敗";
      const parsed: Record<string, string> = {};
      for (const part of String(detail).split("; ")) {
        const [key, ...rest] = part.split(": ");
        if (key && rest.length) parsed[key.trim()] = rest.join(": ");
      }
      setFieldErrors(parsed);
      setBanner({ kind: "err", msg: detail });
    } finally {
      setSaving(false);
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 p-8 text-on-surface-variant">
        <Loader2 className="h-4 w-4 animate-spin" /> 載入設定結構…
      </div>
    );
  }
  if (error) {
    return (
      <div className="flex items-center gap-2 p-8 text-error">
        <AlertCircle className="h-4 w-4" /> 無法載入設定結構。
      </div>
    );
  }

  const group = groups.find((g) => g.id === active);

  return (
    <div className="space-y-4">
      {!hideGroupTabs && groups.length > 1 && (
        <div className="flex flex-wrap gap-1 border-b border-outline-variant/20 pb-2">
          {groups.map((g) => {
            const n = g.fields.filter((f) => f.key in edits).length;
            return (
              <button
                key={g.id}
                onClick={() => setActive(g.id)}
                className={cn(
                  "rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
                  active === g.id
                    ? "bg-primary text-on-primary"
                    : "text-on-surface-variant hover:bg-surface-variant",
                )}
              >
                {g.label_zh || g.label_en}
                {n > 0 && <span className="ml-1.5 text-[10px]">({n})</span>}
              </button>
            );
          })}
        </div>
      )}

      {banner && (
        <div
          className={cn(
            "flex items-start gap-2 rounded-md px-3 py-2 text-sm",
            banner.kind === "ok" ? "bg-primary/10 text-primary" : "bg-error/10 text-error",
          )}
        >
          {banner.kind === "ok" ? (
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
          ) : (
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          )}
          <span className="break-words">{banner.msg}</span>
        </div>
      )}

      {group && (
        <div className="rounded-lg border border-outline-variant/20 px-4">
          {group.fields
            // A dependent field is noise until its switch is on.
            .filter((f) => {
              if (!f.depends) return true;
              const dep = f.depends in edits ? edits[f.depends] : values[f.depends];
              return dep === true || dep === "true";
            })
            .map((f) => (
              <SchemaField
                key={f.key}
                field={f}
                value={valueOf(f)}
                onChange={onChange}
                error={fieldErrors[f.key]}
                dirty={f.key in edits}
              />
            ))}
        </div>
      )}

      <div className="flex items-center justify-end gap-3">
        {dirtyCount > 0 && (
          <button
            onClick={() => { setEdits({}); setFieldErrors({}); setBanner(null); }}
            className="text-xs text-on-surface-variant hover:text-on-surface"
          >
            捨棄變更
          </button>
        )}
        <button
          onClick={save}
          disabled={saving || dirtyCount === 0}
          className={cn(
            "inline-flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-colors",
            dirtyCount === 0
              ? "bg-surface-variant text-on-surface-variant cursor-not-allowed"
              : "bg-primary text-on-primary hover:opacity-90",
          )}
        >
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          儲存{dirtyCount > 0 ? ` (${dirtyCount})` : ""}
        </button>
      </div>
    </div>
  );
}
