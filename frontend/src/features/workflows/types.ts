export interface WorkflowSummary {
  id: string;
  version: number;
  description: string;
  node_count: number;
  layer_count: number;
  valid: boolean;
  error: string | null;
}

export interface WorkflowDetail {
  id: string;
  version: number;
  description: string;
  yaml: string;
  /** Derived by the executor from the key wiring — not declared in the file. */
  layers: string[][];
  valid: boolean;
  error: string | null;
}

export interface ValidateResult {
  valid: boolean;
  layers: string[][];
  node_count: number;
  error: string | null;
}
