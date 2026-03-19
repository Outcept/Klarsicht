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
    <div className="min-h-screen bg-gray-950 text-gray-100">
      {/* Header */}
      <header className="border-b border-gray-800 px-6 py-5">
        <div className="mx-auto max-w-6xl flex items-center gap-3">
          <div className="h-8 w-8 rounded-lg bg-indigo-600 flex items-center justify-center text-sm font-bold">
            K
          </div>
          <h1 className="text-xl font-semibold tracking-tight">Klarsicht</h1>
          <span className="text-sm text-gray-500 ml-1">RCA Dashboard</span>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-8">
        <h2 className="text-2xl font-semibold mb-6">Incidents</h2>

        {loading && (
          <div className="flex items-center gap-2 text-gray-400">
            <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            Loading incidents...
          </div>
        )}

        {error && (
          <div className="rounded-lg border border-red-800 bg-red-950 px-4 py-3 text-red-300 text-sm">
            {error}
          </div>
        )}

        {data && Object.keys(data).length === 0 && (
          <p className="text-gray-500">No incidents found.</p>
        )}

        {data && Object.keys(data).length > 0 && (
          <div className="overflow-x-auto rounded-lg border border-gray-800">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800 bg-gray-900/50 text-left text-gray-400">
                  <th className="px-4 py-3 font-medium">Alert</th>
                  <th className="px-4 py-3 font-medium">Namespace</th>
                  <th className="px-4 py-3 font-medium">Pod</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Confidence</th>
                  <th className="px-4 py-3 font-medium">Started</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(data).map(([id, entry]) => {
                  const r = entry.result;
                  return (
                    <tr
                      key={id}
                      className="border-b border-gray-800/50 hover:bg-gray-900/70 transition-colors"
                    >
                      <td className="px-4 py-3">
                        <Link
                          to={`/incidents/${id}`}
                          className="text-indigo-400 hover:text-indigo-300 font-medium hover:underline"
                        >
                          {r?.alert_name ?? id.slice(0, 8)}
                        </Link>
                      </td>
                      <td className="px-4 py-3 text-gray-300">
                        {r?.namespace ?? "-"}
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-gray-400">
                        {r?.pod ?? "-"}
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge status={entry.status} />
                      </td>
                      <td className="px-4 py-3">
                        {r?.root_cause
                          ? `${Math.round(r.root_cause.confidence * 100)}%`
                          : "-"}
                      </td>
                      <td className="px-4 py-3 text-gray-400">
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
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const isCompleted = status === "completed";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${
        isCompleted
          ? "bg-emerald-950 text-emerald-400 border border-emerald-800"
          : "bg-amber-950 text-amber-400 border border-amber-800"
      }`}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${
          isCompleted ? "bg-emerald-400" : "bg-amber-400 animate-pulse"
        }`}
      />
      {isCompleted ? "Completed" : "Investigating"}
    </span>
  );
}
