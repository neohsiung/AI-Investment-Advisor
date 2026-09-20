export type FieldType =
  | "string" | "secret" | "int" | "float" | "bool"
  | "enum" | "json" | "list" | "cron" | "time";

export interface SettingsField {
  key: string;
  type: FieldType;
  label_en: string;
  label_zh: string;
  help_en: string;
  help_zh: string;
  default: unknown;
  enum: (string | number)[] | null;
  min: number | null;
  max: number | null;
  secret: boolean;
  danger: boolean;
  restart: boolean;
  depends: string | null;
  /** Secrets never carry their value — only whether one is stored. */
  has_value: boolean;
}

export interface SettingsGroup {
  id: string;
  label_en: string;
  label_zh: string;
  fields: SettingsField[];
}

export interface SettingsSchemaResponse {
  status: string;
  version: number;
  groups: SettingsGroup[];
}
