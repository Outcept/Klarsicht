import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchIncidents } from "../lib/api";
import type { IncidentsResponse } from "../lib/types";

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function IncidentList() {
  const [data, setData] = useState<IncidentsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchIncidents()
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="text-xl font-semibold tracking-tight">Incidents</h2>
          <p className="text-sm text-[#888] mt-1">Root cause analyses from fired alerts</p>
        </div>
        <StatusIndicator connected={!error} />
      </div>

      {loading && (
        <div className="flex items-center gap-3 text-[#888] py-20 justify-center">
          <Spinner />
          <span className="text-sm">Loading incidents...</span>
        </div>
      )}

      {error && (
        <div className="rounded-md border border-red-500/20 bg-red-500/5 px-4 py-3 text-red-400 text-sm">
          {error}
        </div>
      )}

      {data && Object.keys(data).length === 0 && (
        <div className="border border-white/[0.08] rounded-md py-16 text-center">
          <p className="text-[#888] text-sm">No incidents yet</p>
          <p className="text-[#555] text-xs mt-1">
            Incidents will appear here when Grafana fires an alert.{" "}
            <Link to="/setup" className="text-white hover:underline">Set up integration</Link>
          </p>
        </div>
      )}

      {data && Object.keys(data).length > 0 && (
        <div className="border border-white/[0.08] rounded-md overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/[0.08] text-left text-[#888]">
                <th className="px-4 py-3 font-medium text-xs uppercase tracking-wider">Alert</th>
                <th className="px-4 py-3 font-medium text-xs uppercase tracking-wider">Namespace</th>
                <th className="px-4 py-3 font-medium text-xs uppercase tracking-wider">Pod</th>
                <th className="px-4 py-3 font-medium text-xs uppercase tracking-wider">Status</th>
                <th className="px-4 py-3 font-medium text-xs uppercase tracking-wider">Confidence</th>
                <th className="px-4 py-3 font-medium text-xs uppercase tracking-wider">Time</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(data).map(([id, entry]) => {
                const r = entry.result;
                return (
                  <tr
                    key={id}
                    className="border-b border-white/[0.04] hover:bg-white/[0.02] transition-colors"
                  >
                    <td className="px-4 py-3">
                      <Link
                        to={`/incidents/${id}`}
                        className="text-white hover:underline underline-offset-4 decoration-white/30 font-medium"
                      >
                        {r?.alert_name ?? id.slice(0, 8)}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-[#888]">
                      {r?.namespace && (
                        <span className="font-mono text-xs bg-white/[0.05] rounded px-1.5 py-0.5">
                          {r.namespace}
                        </span>
                      )}
                      {!r?.namespace && "-"}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-[#888]">
                      {r?.pod ?? "-"}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={entry.status} />
                    </td>
                    <td className="px-4 py-3 font-mono text-xs">
                      {r?.root_cause ? (
                        <span className={r.root_cause.confidence >= 0.8 ? "text-[#22c55e]" : "text-[#888]"}>
                          {Math.round(r.root_cause.confidence * 100)}%
                        </span>
                      ) : (
                        <span className="text-[#555]">-</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-[#888] text-xs">
                      {r?.started_at ? formatTime(r.started_at) : "-"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}

function StatusBadge({ status }: { status: string }) {
  const { dot, text, label } =
    status === "completed"
      ? { dot: "bg-[#22c55e]", text: "text-[#22c55e]", label: "Resolved" }
      : status === "failed"
        ? { dot: "bg-red-500", text: "text-red-400", label: "Failed" }
        : { dot: "bg-amber-400 animate-pulse", text: "text-amber-400", label: "Investigating" };
  return (
    <span className="inline-flex items-center gap-1.5 text-xs">
      <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
      <span className={text}>{label}</span>
    </span>
  );
}

function StatusIndicator({ connected }: { connected: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-[#888]">
      <span className={`h-1.5 w-1.5 rounded-full ${connected ? "bg-[#22c55e]" : "bg-red-500"}`} />
      {connected ? "Connected" : "Disconnected"}
    </span>
  );
}

function Spinner() {
  return (
    <svg className="animate-spin h-4 w-4 text-[#888]" viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  );
}
