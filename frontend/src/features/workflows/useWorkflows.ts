import useSWR from "swr";
import { fetcher } from "@/lib/api";
import type { WorkflowSummary, WorkflowDetail } from "./types";

export function useWorkflowList() {
  const { data, isLoading, error, mutate } = useSWR<WorkflowSummary[]>(
    "/api/v1/workflows",
    fetcher,
    { revalidateOnFocus: false },
  );
  return { workflows: data ?? [], isLoading, error, refresh: mutate };
}

export function useWorkflow(id: string | null) {
  const { data, isLoading, error, mutate } = useSWR<WorkflowDetail>(
    id ? `/api/v1/workflows/${id}` : null,
    fetcher,
    { revalidateOnFocus: false },
  );
  return { workflow: data, isLoading, error, refresh: mutate };
}

/** The code-node palette: name -> one-line description. */
export function useNodePalette() {
  const { data } = useSWR<Record<string, string>>(
    "/api/v1/workflows/nodes",
    fetcher,
    { revalidateOnFocus: false },
  );
  return data ?? {};
}
