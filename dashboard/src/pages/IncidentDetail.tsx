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
      className="ml-2 shrink-0 rounded px-2 py-0.5 text-xs text-[#888] hover:text-white hover:bg-white/[0.08] transition-colors"
    >
      {copied ? "Copied" : "Copy"}
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
      <Page>
        <div className="flex items-center gap-3 text-[#888] py-20 justify-center">
          <Spinner />
          <span className="text-sm">Loading...</span>
        </div>
      </Page>
    );
  }

  if (error) {
    return (
      <Page>
        <div className="rounded-md border border-red-500/20 bg-red-500/5 px-4 py-3 text-red-400 text-sm">
          {error}
        </div>
      </Page>
    );
  }

  if (!data) {
    return (
      <Page>
        <p className="text-[#888]">Incident not found.</p>
      </Page>
    );
  }

  const r = data.result;
  const isCompleted = data.status === "completed";

  return (
    <Page>
      {/* Back */}
      <Link
        to="/"
        className="inline-flex items-center gap-1.5 text-sm text-[#888] hover:text-white transition-colors mb-8"
      >
        <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
        Back
      </Link>

      {/* Header */}
      <div className="border border-white/[0.08] rounded-md p-6 mb-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-xl font-semibold tracking-tight mb-2">
              {r?.alert_name ?? id}
            </h2>
            <div className="flex flex-wrap items-center gap-2">
              {r?.namespace && <Tag>{r.namespace}</Tag>}
              {r?.pod && <Tag>{r.pod}</Tag>}
            </div>
          </div>
          <div className="flex flex-col items-end gap-2">
            <StatusBadge status={data.status} />
            {r?.root_cause && <CategoryTag category={r.root_cause.category} />}
          </div>
        </div>
        {r && (
          <div className="mt-5 flex flex-wrap gap-8 text-xs text-[#888] border-t border-white/[0.08] pt-4">
            <div>
              <span className="text-[#555]">Started</span>{" "}
              <span className="font-mono">{formatTimestamp(r.started_at)}</span>
            </div>
            <div>
              <span className="text-[#555]">Investigated</span>{" "}
              <span className="font-mono">{formatTimestamp(r.investigated_at)}</span>
            </div>
          </div>
        )}
      </div>

      {!r && !isCompleted && (
        <div className="border border-white/[0.08] rounded-md px-6 py-12 text-center">
          <div className="inline-flex items-center gap-2 text-amber-400 text-sm mb-2">
            <span className="h-1.5 w-1.5 rounded-full bg-amber-400 animate-pulse" />
            Investigation in progress
          </div>
          <p className="text-xs text-[#888]">Results will appear here once the analysis is complete.</p>
        </div>
      )}

      {r && (
        <div className="space-y-6">
          {/* Root Cause */}
          <section className="border border-white/[0.08] rounded-md p-6">
            <SectionTitle>Root Cause</SectionTitle>
            <p className="text-white/90 mb-5">{r.root_cause.summary}</p>

            {/* Confidence */}
            <div className="mb-5">
              <div className="flex items-center justify-between text-xs mb-2">
                <span className="text-[#888]">Confidence</span>
                <span className={`font-mono font-medium ${
                  r.root_cause.confidence >= 0.8 ? "text-[#22c55e]" : "text-[#888]"
                }`}>
                  {Math.round(r.root_cause.confidence * 100)}%
                </span>
              </div>
              <div className="h-1 rounded-full bg-white/[0.08] overflow-hidden">
                <div
                  className="h-full rounded-full bg-[#22c55e] transition-all duration-500"
                  style={{ width: `${r.root_cause.confidence * 100}%` }}
                />
              </div>
            </div>

            {/* Evidence */}
            {r.root_cause.evidence.length > 0 && (
              <div>
                <h4 className="text-xs font-medium text-[#888] uppercase tracking-wider mb-3">Evidence</h4>
                <ul className="space-y-2">
                  {r.root_cause.evidence.map((item, i) => (
                    <li key={i} className="flex items-start gap-2.5 text-sm text-white/70">
                      <span className="mt-1.5 h-1 w-1 rounded-full bg-[#555] shrink-0" />
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>

          {/* Fix Steps */}
          {r.fix_steps.length > 0 && (
            <section className="border border-white/[0.08] rounded-md p-6">
              <SectionTitle>Fix Steps</SectionTitle>
              <ol className="space-y-4">
                {r.fix_steps.map((step) => (
                  <li key={step.order} className="flex gap-3">
                    <span className="shrink-0 flex h-6 w-6 items-center justify-center rounded-full border border-white/[0.15] text-xs font-medium text-[#888]">
                      {step.order}
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-white/90 mb-1">{step.description}</p>
                      {step.command && (
                        <div className="flex items-center rounded border border-white/[0.08] bg-white/[0.02] px-3 py-2 mt-1.5">
                          <code className="text-xs text-[#22c55e] font-mono break-all flex-1">
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
            <section className="border border-white/[0.08] rounded-md p-6">
              <SectionTitle>Postmortem</SectionTitle>

              {r.postmortem.impact && (
                <div className="mb-6">
                  <h4 className="text-xs font-medium text-[#888] uppercase tracking-wider mb-2">Impact</h4>
                  <p className="text-sm text-white/80">{r.postmortem.impact}</p>
                </div>
              )}

              {r.postmortem.timeline.length > 0 && (
                <div className="mb-6">
                  <h4 className="text-xs font-medium text-[#888] uppercase tracking-wider mb-3">Timeline</h4>
                  <div className="relative pl-4 border-l border-white/[0.08] space-y-3">
                    {r.postmortem.timeline.map((entry, i) => (
                      <div key={i} className="relative">
                        <div className="absolute -left-[calc(0.25rem+3px)] top-1.5 h-1.5 w-1.5 rounded-full bg-[#555]" />
                        <p className="text-xs text-[#555] font-mono mb-0.5">
                          {formatTimestamp(entry.timestamp)}
                        </p>
                        <p className="text-sm text-white/70">{entry.event}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {r.postmortem.action_items.length > 0 && (
                <div>
                  <h4 className="text-xs font-medium text-[#888] uppercase tracking-wider mb-2">Action Items</h4>
                  <ul className="space-y-2">
                    {r.postmortem.action_items.map((item, i) => (
                      <li key={i} className="flex items-start gap-2.5 text-sm text-white/70">
                        <span className="mt-0.5 h-4 w-4 shrink-0 rounded border border-white/[0.15]" />
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
    </Page>
  );
}

function Page({ children }: { children: React.ReactNode }) {
  return <main className="mx-auto max-w-5xl px-6 py-10">{children}</main>;
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h3 className="text-sm font-semibold uppercase tracking-wider text-[#888] mb-4">{children}</h3>;
}

function Tag({ children }: { children: React.ReactNode }) {
  return (
    <span className="font-mono text-xs bg-white/[0.05] border border-white/[0.08] rounded px-1.5 py-0.5 text-[#888]">
      {children}
    </span>
  );
}

function StatusBadge({ status }: { status: string }) {
  const isCompleted = status === "completed";
  return (
    <span className="inline-flex items-center gap-1.5 text-xs">
      <span className={`h-1.5 w-1.5 rounded-full ${isCompleted ? "bg-[#22c55e]" : "bg-amber-400 animate-pulse"}`} />
      <span className={isCompleted ? "text-[#22c55e]" : "text-amber-400"}>
        {isCompleted ? "Resolved" : "Investigating"}
      </span>
    </span>
  );
}

function CategoryTag({ category }: { category: string }) {
  return (
    <span className="rounded border border-white/[0.08] bg-white/[0.03] px-2 py-0.5 text-xs text-[#888]">
      {category}
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
