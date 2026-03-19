import type { IncidentEntry, IncidentsResponse } from "./types";

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
