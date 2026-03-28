import type { IncidentEntry, IncidentsResponse, InvestigationProgress, StatsResponse } from "./types";

const BASE = "/api";

export async function fetchIncidents(): Promise<IncidentsResponse> {
  const res = await fetch(`${BASE}/incidents`);
  if (!res.ok) throw new Error(`Failed to fetch incidents: ${res.status}`);
  return res.json();
}

export async function fetchIncident(id: string): Promise<IncidentEntry> {
  const res = await fetch(`${BASE}/incidents/${encodeURIComponent(id)}`);
  if (!res.ok) throw new Error(`Failed to fetch incident ${id}: ${res.status}`);
  return res.json();
}

export async function fetchStats(): Promise<StatsResponse> {
  const res = await fetch(`${BASE}/stats`);
  if (!res.ok) throw new Error(`Failed to fetch stats: ${res.status}`);
  return res.json();
}

export async function fetchSteps(id: string): Promise<InvestigationProgress> {
  const res = await fetch(`${BASE}/incidents/${encodeURIComponent(id)}/steps`);
  if (!res.ok) throw new Error(`Failed to fetch steps: ${res.status}`);
  return res.json();
}
