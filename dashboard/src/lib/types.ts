export interface FixStep {
  order: number;
  description: string;
  command?: string;
}

export interface TimelineEntry {
  timestamp: string;
  event: string;
}

export interface RootCause {
  summary: string;
  confidence: number;
  category: string;
  evidence: string[];
}

export interface Postmortem {
  timeline: TimelineEntry[];
  impact: string;
  action_items: string[];
}

export interface RCAResult {
  incident_id: string;
  alert_name: string;
  namespace: string;
  pod: string;
  started_at: string;
  investigated_at: string;
  root_cause: RootCause;
  fix_steps: FixStep[];
  postmortem: Postmortem;
}

export interface IncidentEntry {
  status: "completed" | "investigating";
  result: RCAResult | null;
}

export type IncidentsResponse = Record<string, IncidentEntry>;
