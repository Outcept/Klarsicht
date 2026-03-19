import { useEffect, useState, useCallback } from "react";
import { useParams, Link } from "react-router-dom";
import { fetchIncident } from "../lib/api";
import type { IncidentEntry } from "../lib/types";

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [text]);

  return (
    <button
      onClick={handleCopy}
      className="ml-2 shrink-0 rounded px-2 py-1 text-xs text-gray-400 hover:text-gray-200 hover:bg-gray-700 transition-colors"
      title="Copy to clipboard"
    >
      {copied ? "Copied!" : "Copy"}
    </button>
  );
}

export default function IncidentDetail() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<IncidentEntry | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    fetchIncident(id)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <Shell>
        <div className="flex items-center gap-2 text-gray-400 py-20 justify-center">
          <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          Loading...
        </div>
      </Shell>
    );
  }

  if (error) {
    return (
      <Shell>
        <div className="rounded-lg border border-red-800 bg-red-950 px-4 py-3 text-red-300 text-sm">
          {error}
        </div>
      </Shell>
    );
  }

  if (!data) {
    return (
      <Shell>
        <p className="text-gray-500">Incident not found.</p>
      </Shell>
    );
  }

  const r = data.result;
  const isCompleted = data.status === "completed";

  return (
    <Shell>
      {/* Back link */}
      <Link
        to="/"
        className="inline-flex items-center gap-1 text-sm text-gray-400 hover:text-gray-200 mb-6 transition-colors"
      >
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
        Back to incidents
      </Link>

      {/* Header */}
      <div className="rounded-lg border border-gray-800 bg-gray-900/50 p-6 mb-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-2xl font-semibold mb-2">
              {r?.alert_name ?? id}
            </h2>
            <div className="flex flex-wrap items-center gap-2 text-sm text-gray-400">
              {r?.namespace && (
                <span className="rounded bg-gray-800 px-2 py-0.5 font-mono text-xs">
                  {r.namespace}
                </span>
              )}
              {r?.pod && (
                <span className="rounded bg-gray-800 px-2 py-0.5 font-mono text-xs">
                  {r.pod}
                </span>
              )}
            </div>
          </div>
          <div className="flex flex-col items-end gap-2">
            <StatusBadge status={data.status} />
            {r?.root_cause && (
              <CategoryTag category={r.root_cause.category} />
            )}
          </div>
        </div>

        {r && (
          <div className="mt-4 flex flex-wrap gap-6 text-sm text-gray-400 border-t border-gray-800 pt-4">
            <div>
              <span className="text-gray-500">Started:</span>{" "}
              {formatTimestamp(r.started_at)}
            </div>
            <div>
              <span className="text-gray-500">Investigated:</span>{" "}
              {formatTimestamp(r.investigated_at)}
            </div>
          </div>
        )}
      </div>

      {!r && isCompleted && (
        <p className="text-gray-500">Result data is not available yet.</p>
      )}

      {!r && !isCompleted && (
        <div className="rounded-lg border border-amber-800/50 bg-amber-950/30 px-6 py-8 text-center">
          <p className="text-amber-300 font-medium mb-1">Investigation in progress</p>
          <p className="text-sm text-gray-400">Results will appear here once the analysis is complete.</p>
        </div>
      )}

      {r && (
        <div className="space-y-6">
          {/* Root Cause */}
          <section className="rounded-lg border border-gray-800 bg-gray-900/50 p-6">
            <h3 className="text-lg font-semibold mb-4">Root Cause</h3>

            <p className="text-gray-200 mb-4">{r.root_cause.summary}</p>

            {/* Confidence bar */}
            <div className="mb-4">
              <div className="flex items-center justify-between text-sm mb-1.5">
                <span className="text-gray-400">Confidence</span>
                <span className="font-mono font-medium">
                  {Math.round(r.root_cause.confidence * 100)}%
                </span>
              </div>
              <div className="h-2 rounded-full bg-gray-800 overflow-hidden">
                <div
                  className="h-full rounded-full bg-indigo-500 transition-all"
                  style={{ width: `${r.root_cause.confidence * 100}%` }}
                />
              </div>
            </div>

            {/* Evidence */}
            {r.root_cause.evidence.length > 0 && (
              <div>
                <h4 className="text-sm font-medium text-gray-400 mb-2">Evidence</h4>
                <ul className="space-y-1.5">
                  {r.root_cause.evidence.map((item, i) => (
                    <li
                      key={i}
                      className="text-sm text-gray-300 pl-4 relative before:content-[''] before:absolute before:left-0 before:top-2 before:h-1.5 before:w-1.5 before:rounded-full before:bg-gray-600"
                    >
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>

          {/* Fix Steps */}
          {r.fix_steps.length > 0 && (
            <section className="rounded-lg border border-gray-800 bg-gray-900/50 p-6">
              <h3 className="text-lg font-semibold mb-4">Fix Steps</h3>
              <ol className="space-y-4">
                {r.fix_steps.map((step) => (
                  <li key={step.order} className="flex gap-3">
                    <span className="shrink-0 flex h-6 w-6 items-center justify-center rounded-full bg-indigo-900 text-xs font-bold text-indigo-300">
                      {step.order}
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className="text-gray-200 text-sm mb-1">{step.description}</p>
                      {step.command && (
                        <div className="flex items-center rounded bg-gray-950 border border-gray-800 px-3 py-2 mt-1">
                          <code className="text-xs text-emerald-400 font-mono break-all flex-1">
                            {step.command}
                          </code>
                          <CopyButton text={step.command} />
                        </div>
                      )}
                    </div>
                  </li>
                ))}
              </ol>
            </section>
          )}

          {/* Postmortem */}
          {r.postmortem && (
            <section className="rounded-lg border border-gray-800 bg-gray-900/50 p-6">
              <h3 className="text-lg font-semibold mb-4">Postmortem</h3>

              {/* Impact */}
              <div className="mb-6">
                <h4 className="text-sm font-medium text-gray-400 mb-1">Impact</h4>
                <p className="text-gray-200 text-sm">{r.postmortem.impact}</p>
              </div>

              {/* Timeline */}
              {r.postmortem.timeline.length > 0 && (
                <div className="mb-6">
                  <h4 className="text-sm font-medium text-gray-400 mb-3">Timeline</h4>
                  <div className="relative pl-4 border-l-2 border-gray-800 space-y-3">
                    {r.postmortem.timeline.map((entry, i) => (
                      <div key={i} className="relative">
                        <div className="absolute -left-[calc(0.25rem+5px)] top-1.5 h-2 w-2 rounded-full bg-gray-600" />
                        <p className="text-xs text-gray-500 font-mono mb-0.5">
                          {formatTimestamp(entry.timestamp)}
                        </p>
                        <p className="text-sm text-gray-300">{entry.event}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Action Items */}
              {r.postmortem.action_items.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-gray-400 mb-2">Action Items</h4>
                  <ul className="space-y-1.5">
                    {r.postmortem.action_items.map((item, i) => (
                      <li
                        key={i}
                        className="flex items-start gap-2 text-sm text-gray-300"
                      >
                        <span className="mt-0.5 h-4 w-4 shrink-0 rounded border border-gray-600" />
                        {item}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </section>
          )}
        </div>
      )}
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <header className="border-b border-gray-800 px-6 py-5">
        <div className="mx-auto max-w-6xl flex items-center gap-3">
          <div className="h-8 w-8 rounded-lg bg-indigo-600 flex items-center justify-center text-sm font-bold">
            K
          </div>
          <h1 className="text-xl font-semibold tracking-tight">Klarsicht</h1>
          <span className="text-sm text-gray-500 ml-1">RCA Dashboard</span>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
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

function CategoryTag({ category }: { category: string }) {
  const colors: Record<string, string> = {
    misconfiguration: "bg-violet-950 text-violet-400 border-violet-800",
    oom: "bg-red-950 text-red-400 border-red-800",
    crash: "bg-orange-950 text-orange-400 border-orange-800",
    networking: "bg-blue-950 text-blue-400 border-blue-800",
    scaling: "bg-cyan-950 text-cyan-400 border-cyan-800",
  };
  const cls = colors[category.toLowerCase()] ?? "bg-gray-800 text-gray-400 border-gray-700";
  return (
    <span className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${cls}`}>
      {category}
    </span>
  );
}
