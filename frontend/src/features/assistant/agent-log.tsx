"use client";

import { useCallback, useEffect, useState } from "react";

import { MockBadge } from "@/components/mock-badge";
import { Button } from "@/components/ui/button";
import { ApiError, api, type Schemas } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

import { AGENT_LABELS } from "./chat-panel";

type Log = Schemas["AgentLogOut"];
type Call = Schemas["MemoryCallOut"];

const PHASES: [string, string][] = [
  ["records_ms", "records"],
  ["recall_ms", "memory recall"],
  ["agents_ms", "agents"],
  ["compose_ms", "reply"],
];

const seconds = (ms: number) => (ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${ms} ms`);

/** What happened on each turn, including every Meko call, so it is visible that memory is live. */
export function AgentLog({ userId, refreshKey }: { userId: string; refreshKey: number }) {
  const [logs, setLogs] = useState<Log[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchLogs = useCallback(
    () =>
      api("get", "/api/assistant/logs", { query: { user_id: userId, limit: 10 } })
        .then((r) => {
          setLogs(r.logs);
          setError(null);
        })
        .catch((err) => setError(err instanceof ApiError ? err.message : "Couldn't load the log.")),
    [userId],
  );

  async function refresh() {
    setLoading(true);
    await fetchLogs();
    setLoading(false);
  }

  useEffect(() => {
    void fetchLogs();
    // Memories are saved just after a reply; look again shortly to show those calls too.
    const later = setTimeout(() => void fetchLogs(), 8000);
    return () => clearTimeout(later);
  }, [fetchLogs, refreshKey]);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">The last 10 turns, newest first</p>
        <Button variant="ghost" className="h-8 px-3" onClick={() => void refresh()} disabled={loading}>
          {loading ? "Loading…" : "Refresh"}
        </Button>
      </div>
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
      {logs?.length === 0 && <p className="text-sm text-muted-foreground">No chats yet.</p>}
      <ol className="flex flex-col gap-3" aria-label="Agent log">
        {logs?.map((log) => (
          <li key={log.run_id} className="rounded-md border border-border bg-card p-3 text-xs">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-semibold text-foreground">
                {log.agents.map((a) => AGENT_LABELS[a] ?? a).join(", ") || "No agents"}
              </span>
              <span className="tabular-nums text-muted-foreground">
                {seconds(log.latency_ms)} · {formatDateTime(log.created_at)}
              </span>
            </div>
            <p className="mt-1 tabular-nums text-muted-foreground">
              {PHASES.filter(([k]) => k in log.timings)
                .map(([k, label]) => `${label} ${seconds(log.timings[k])}`)
                .join(" · ")}
            </p>

            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <span className={cn("font-medium", log.memory.enabled ? "text-primary" : "text-muted-foreground")}>
                Memory {log.memory.enabled ? "ON" : "OFF"}
                {log.memory.enabled && (log.memory.live ? " · live Meko" : log.memory.error ? " · unavailable" : "")}
              </span>
              {log.memory.is_mock && log.memory.enabled && <MockBadge what="memory" />}
            </div>
            {log.memory.error && <p className="mt-1 text-warning">{log.memory.error}</p>}
            {log.memory.calls.length > 0 && <Calls title="Recall" calls={log.memory.calls} />}
            {log.memory.enabled && log.memory.live && (
              log.memory.commit_calls ? (
                log.memory.commit_calls.length > 0 && <Calls title="Saved after the reply" calls={log.memory.commit_calls} />
              ) : log.memory.written === 0 ? (
                <p className="mt-1 text-muted-foreground">Nothing new to save</p>
              ) : log.memory.written ? (
                <p className="mt-1 text-muted-foreground">Saving {log.memory.written} after the reply…</p>
              ) : null
            )}

            <p className="mt-2 text-muted-foreground">
              {log.llm.used
                ? `Reply written by ${log.llm.model}`
                : `Template reply${log.llm.fallback_reason ? ` (${log.llm.fallback_reason.replace(/_/g, " ")})` : ""}`}
              {log.llm.is_mock ? " · mock" : ""}
            </p>
          </li>
        ))}
      </ol>
    </div>
  );
}

function Calls({ title, calls }: { title: string; calls: Call[] }) {
  return (
    <div className="mt-1">
      <p className="text-muted-foreground">{title}:</p>
      <ul className="mt-0.5 flex flex-col gap-0.5 font-mono">
        {calls.map((c, i) => (
          <li key={`${c.tool}-${i}`} className={cn("tabular-nums", c.ok ? "text-foreground" : "text-danger")}>
            <span aria-label={c.ok ? "ok" : "failed"}>{c.ok ? "✓" : "✕"}</span> {c.tool} {seconds(c.latency_ms)}
            {c.error ? `: ${c.error}` : ""}
          </li>
        ))}
      </ul>
    </div>
  );
}
