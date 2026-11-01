"use client";

import { useEffect, useState } from "react";

import { MockBadge } from "@/components/mock-badge";
import { api, type Schemas } from "@/lib/api";

type State = { kind: "loading" } | { kind: "offline" } | { kind: "ok"; health: Schemas["HealthResponse"] };

/** Header pill: is the backend up, and which dependencies are mocks. */
export function BackendStatus() {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    const ctrl = new AbortController();
    api("get", "/api/health", { signal: ctrl.signal, timeoutMs: 10_000 })
      .then((health) => setState({ kind: "ok", health }))
      .catch(() => {
        if (!ctrl.signal.aborted) setState({ kind: "offline" });
      });
    return () => ctrl.abort();
  }, []);

  if (state.kind === "loading") return null;
  if (state.kind === "offline") {
    return <Pill className="border-danger text-danger">Server offline</Pill>;
  }
  const mocks = Object.entries(state.health.dependencies).filter(([, d]) => d.is_mock).map(([name]) => name);
  return (
    <div className="flex flex-wrap items-center gap-2">
      {state.health.status === "degraded" && <Pill className="border-warning text-warning">Some services limited</Pill>}
      {mocks.map((name) => (
        <MockBadge key={name} what={name} />
      ))}
    </div>
  );
}

function Pill({ className, children }: { className: string; children: React.ReactNode }) {
  return <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${className}`}>{children}</span>;
}
