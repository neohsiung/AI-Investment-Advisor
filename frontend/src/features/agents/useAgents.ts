import useSWR from "swr";
import { fetcher } from "@/lib/api";
import type { AgentSummary, PromptDetail, PersonaSummary, SwarmRoster } from "./types";

export function useAgents() {
  const { data, isLoading, error, mutate } = useSWR<AgentSummary[]>(
    "/api/v1/agents", fetcher, { revalidateOnFocus: false },
  );
  return { agents: data ?? [], isLoading, error, refresh: mutate };
}

export function useAgentPrompt(id: string | null) {
  const { data, isLoading, mutate } = useSWR<PromptDetail>(
    id ? `/api/v1/agents/${id}/prompt` : null, fetcher, { revalidateOnFocus: false },
  );
  return { prompt: data, isLoading, refresh: mutate };
}

export function usePersonas() {
  const { data } = useSWR<PersonaSummary[]>(
    "/api/v1/agents/personas/all", fetcher, { revalidateOnFocus: false },
  );
  return data ?? [];
}

export function useSwarms() {
  const { data } = useSWR<SwarmRoster[]>(
    "/api/v1/agents/swarms/all", fetcher, { revalidateOnFocus: false },
  );
  return data ?? [];
}
