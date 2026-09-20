import useSWR from "swr";
import { fetcher } from "@/lib/api";
import type { SettingsSchemaResponse } from "./types";

/**
 * The field registry that drives the settings form.
 *
 * Two requests on purpose: the schema describes the fields (and is the same for
 * everyone), while GET /settings carries the stored values. Secrets appear only
 * in the schema response, as `has_value` — their contents never leave the
 * server, so they cannot be read back out of the values payload.
 *
 * 刻意分兩個請求：schema 描述欄位，GET /settings 提供值。
 * secret 只在 schema 中以 has_value 呈現，內容不離開伺服器。
 */
export function useSettingsSchema() {
  const schema = useSWR<SettingsSchemaResponse>("/api/v1/settings/schema", fetcher, {
    revalidateOnFocus: false,
  });
  const values = useSWR<{ data: Record<string, unknown> }>("/api/v1/settings", fetcher, {
    revalidateOnFocus: false,
  });

  return {
    groups: schema.data?.groups ?? [],
    version: schema.data?.version,
    values: values.data?.data ?? {},
    isLoading: schema.isLoading || values.isLoading,
    error: schema.error || values.error,
  };
}
