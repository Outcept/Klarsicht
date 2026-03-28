import { useEffect, useState, useCallback, useRef } from "react";
import { useParams, Link } from "react-router-dom";
import { fetchIncident, fetchSteps } from "../lib/api";
import type { IncidentEntry, InvestigationStep } from "../lib/types";

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

function CopyButton({ text, label }: { text: string; label?: string }) {
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
      className="shrink-0 rounded px-2 py-0.5 text-xs text-[#888] hover:text-white hover:bg-white/[0.08] transition-colors"
    >
      {copied ? "Copied" : label ?? "Copy"}
    </button>
  );
}

function formatPostmortemMarkdown(r: NonNullable<IncidentEntry["result"]>): string {
  const lines: string[] = [];
  lines.push(`# Postmortem: ${r.alert_name}`);
  lines.push("");
  lines.push(`**Namespace:** ${r.namespace}  `);
  lines.push(`**Pod:** ${r.pod}  `);
  lines.push(`**Started:** ${r.started_at}  `);
  lines.push(`**Investigated:** ${r.investigated_at}`);
  lines.push("");

  if (r.root_cause) {
    lines.push("## Root Cause");
    lines.push("");
    lines.push(r.root_cause.summary);
    lines.push("");
    lines.push(`**Confidence:** ${Math.round(r.root_cause.confidence * 100)}%  `);
    lines.push(`**Category:** ${r.root_cause.category}`);
    if (r.root_cause.evidence.length > 0) {
      lines.push("");
      lines.push("### Evidence");
      lines.push("");
      r.root_cause.evidence.forEach((e) => lines.push(`- ${e}`));
    }
    lines.push("");
  }

  if (r.fix_steps.length > 0) {
    lines.push("## Fix Steps");
    lines.push("");
    r.fix_steps.forEach((s) => {
      lines.push(`${s.order}. ${s.description}`);
      if (s.command) lines.push(`   \`\`\`\n   ${s.command}\n   \`\`\``);
    });
    lines.push("");
  }

  if (r.postmortem) {
    if (r.postmortem.impact) {
      lines.push("## Impact");
      lines.push("");
      lines.push(r.postmortem.impact);
      lines.push("");
    }
    if (r.postmortem.timeline.length > 0) {
      lines.push("## Timeline");
      lines.push("");
      lines.push("| Time | Event |");
      lines.push("|------|-------|");
      r.postmortem.timeline.forEach((t) => lines.push(`| ${t.timestamp} | ${t.event} |`));
      lines.push("");
    }
    if (r.postmortem.action_items.length > 0) {
      lines.push("## Action Items");
      lines.push("");
      r.postmortem.action_items.forEach((a) => lines.push(`- [ ] ${a}`));
      lines.push("");
    }
  }

  return lines.join("\n");
}

export default function IncidentDetail() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<IncidentEntry | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [steps, setSteps] = useState<InvestigationStep[]>([]);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!id) return;
    fetchIncident(id)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  // Poll for steps and auto-refresh when investigating
  useEffect(() => {
    if (!id || !data) return;
    if (data.status !== "investigating") return;

    const poll = async () => {
      try {
        const progress = await fetchSteps(id);
        setSteps(progress.steps);
        if (progress.status === "completed" || progress.status === "failed") {
          // Investigation done — refresh the incident data
          const updated = await fetchIncident(id);
          setData(updated);
          if (pollRef.current) clearInterval(pollRef.current);
        }
      } catch { /* ignore */ }
    };

    poll(); // immediate first call
    pollRef.current = setInterval(poll, 3000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [id, data?.status]);

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
        to="/incidents"
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
        <div className="border border-white/[0.08] rounded-md p-6">
          <div className="flex items-center gap-2 text-amber-400 text-sm mb-4">
            <span className="h-1.5 w-1.5 rounded-full bg-amber-400 animate-pulse" />
            Investigation in progress
          </div>
          {steps.length > 0 ? (
            <div className="relative pl-4 border-l border-white/[0.08] space-y-3">
              {steps.map((step, i) => (
                <div key={i} className="relative">
                  <div className={`absolute -left-[calc(0.25rem+3px)] top-1.5 h-1.5 w-1.5 rounded-full ${
                    step.status === "done" ? "bg-[#22c55e]" :
                    step.status === "error" ? "bg-red-500" :
                    i === steps.length - 1 ? "bg-amber-400 animate-pulse" : "bg-[#555]"
                  }`} />
                  <p className={`text-sm font-medium ${
                    step.status === "error" ? "text-red-400" :
                    step.status === "done" ? "text-white/90" : "text-white"
                  }`}>
                    {step.event}
                  </p>
                  {step.detail && (
                    <p className="text-xs text-[#555] font-mono mt-0.5 truncate">{step.detail}</p>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-[#888]">Waiting for agent to start...</p>
          )}
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
              <div className="flex items-center justify-between mb-4">
                <SectionTitle>Postmortem</SectionTitle>
                <CopyButton text={formatPostmortemMarkdown(r)} label="Copy as Markdown" />
              </div>

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
