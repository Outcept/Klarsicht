import { useEffect, useState } from "react";
import { authFetch } from "../auth";

interface ServiceStatus {
  name: string;
  status: "ok" | "error" | "disabled";
  error?: string;
}

interface ReadyResponse {
  status: "ok" | "degraded";
  services: ServiceStatus[];
}

function ServiceRow({ svc }: { svc: ServiceStatus }) {
  const [open, setOpen] = useState(false);
  const hasError = svc.status === "error" && Boolean(svc.error);

  return (
    <div className="rounded border border-white/[0.05]">
      <button
        type="button"
        onClick={() => hasError && setOpen(!open)}
        disabled={!hasError}
        className={`w-full flex items-center justify-between px-3 py-2 text-left ${
          hasError ? "hover:bg-white/[0.02] cursor-pointer" : "cursor-default"
        }`}
      >
        <div className="flex items-center gap-3">
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              svc.status === "ok"
                ? "bg-[#22c55e]"
                : svc.status === "error"
                ? "bg-red-500"
                : "bg-[#555]"
            }`}
          />
          <span className="text-sm font-mono text-white/90">{svc.name}</span>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`text-xs font-medium ${
              svc.status === "ok"
                ? "text-[#22c55e]"
                : svc.status === "error"
                ? "text-red-400"
                : "text-[#555]"
            }`}
          >
            {svc.status}
          </span>
          {hasError && (
            <svg
              className={`h-3 w-3 text-[#666] transition-transform ${open ? "rotate-180" : ""}`}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
            </svg>
          )}
        </div>
      </button>
      {open && hasError && (
        <div className="border-t border-white/[0.05] px-3 py-2 bg-white/[0.01]">
          <pre className="text-xs text-red-300/80 font-mono whitespace-pre-wrap break-all">
            {svc.error}
          </pre>
        </div>
      )}
    </div>
  );
}

export default function Admin() {
  const [config, setConfig] = useState<Record<string, unknown> | null>(null);
  const [ready, setReady] = useState<ReadyResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      authFetch("/api/admin/config").then((r) => (r.ok ? r.json() : Promise.reject(`Config: HTTP ${r.status}`))),
      authFetch("/api/readyz").then((r) => r.json()),
    ])
      .then(([cfg, rdy]) => {
        setConfig(cfg);
        setReady(rdy);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <main className="mx-auto max-w-5xl px-6 py-10">
        <p className="text-sm text-[#888]">Loading…</p>
      </main>
    );
  }

  if (error) {
    return (
      <main className="mx-auto max-w-5xl px-6 py-10">
        <div className="rounded-md border border-red-500/20 bg-red-500/5 px-4 py-3 text-red-400 text-sm">
          {error}
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-5xl px-6 py-10 space-y-8">
      <div>
        <h2 className="text-xl font-semibold tracking-tight mb-1">Admin</h2>
        <p className="text-sm text-[#888]">Service health and running configuration.</p>
      </div>

      {/* Service health */}
      <section className="border border-white/[0.08] rounded-md p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-[#888]">Service Health</h3>
          {ready && (
            <span
              className={`inline-flex items-center gap-1.5 text-xs ${
                ready.status === "ok" ? "text-[#22c55e]" : "text-amber-400"
              }`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  ready.status === "ok" ? "bg-[#22c55e]" : "bg-amber-400"
                }`}
              />
              {ready.status === "ok" ? "All services healthy" : "Degraded"}
            </span>
          )}
        </div>

        <div className="space-y-2">
          {ready?.services.map((svc) => (
            <ServiceRow key={svc.name} svc={svc} />
          ))}
        </div>
      </section>

      {/* Config */}
      <section className="border border-white/[0.08] rounded-md p-6">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-[#888] mb-4">Configuration</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-2 text-xs">
          {config &&
            Object.entries(config).map(([key, value]) => (
              <div key={key} className="flex items-baseline gap-2 border-b border-white/[0.04] py-1.5">
                <span className="text-[#666] font-mono shrink-0 min-w-[160px]">{key}</span>
                <span className="text-white/80 font-mono break-all">
                  {value === null || value === undefined || value === ""
                    ? <span className="text-[#444]">—</span>
                    : typeof value === "object"
                    ? JSON.stringify(value)
                    : String(value)}
                </span>
              </div>
            ))}
        </div>
      </section>
    </main>
  );
}
