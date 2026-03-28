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

export interface InvestigationStep {
  timestamp: number;
  event: string;
  detail: string;
  tool: string;
  status: "running" | "done" | "error";
}

export interface InvestigationProgress {
  status: "investigating" | "completed" | "failed";
  steps: InvestigationStep[];
}

export interface StatsRecentIncident {
  incident_id: string;
  alert_name: string;
  namespace: string;
  pod: string;
  status: "completed" | "investigating" | "failed";
  confidence: number | null;
  started_at: string | null;
}

export interface StatsResponse {
  total_incidents: number;
  completed: number;
  investigating: number;
  failed: number;
  avg_investigation_seconds: number;
  top_alerts: { alert_name: string; count: number }[];
  top_namespaces: { namespace: string; count: number }[];
  recent_incidents: StatsRecentIncident[];
  category_breakdown: { category: string; count: number }[];
}
