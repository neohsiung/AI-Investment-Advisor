export interface AgentSummary {
  id: string;
  display_name: string;
  impl: string;
  default_tier: string;
  description: string;
  workspace: string | null;
  persona: string | null;
  enabled: boolean;
  skills: string[];
  has_prompt_override: boolean;
}

/** Which of the four sources supplied the prompt text currently in effect. */
export type PromptSource = "override" | "manifest" | "workspace" | "legacy" | "none";

export interface PromptDetail {
  agent: string;
  prompt: string;
  source: PromptSource;
  has_override: boolean;
}

export interface PersonaSummary {
  name: string;
  display_name: string;
  tone: string;
  body: string;
}

export interface SwarmRoster {
  id: string;
  sub_agents: {
    name: string;
    tier: string;
    column: string | null;
    instruction: string;
  }[];
}
