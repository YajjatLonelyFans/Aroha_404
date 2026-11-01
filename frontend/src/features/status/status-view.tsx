"use client";

import { useCallback, useEffect, useState } from "react";

import { MockBadge } from "@/components/mock-badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ApiError, api, type Schemas } from "@/lib/api";
import { cn } from "@/lib/utils";

type Health = Schemas["HealthResponse"];
type Dep = Schemas["DependencyStatus"];

const NAMES: Record<string, string> = {
  mongo: "Database (MongoDB)",
  open_meteo: "Weather (Open-Meteo)",
  nominatim: "Address search (Nominatim)",
  satellite_imagery: "Satellite imagery",
  meko: "Memory (Meko)",
  llm: "Assistant (Gemini)",
};

// "configured" means the settings are present but the deep check did not call the service.
const STATE: Record<Dep["status"], { label: string; symbol: string; className: string }> = {
  ok: { label: "Working", symbol: "✓", className: "border-success text-success" },
  configured: { label: "Set up, not checked live", symbol: "•", className: "border-warning text-warning" },
  not_configured: { label: "Not set up", symbol: "✕", className: "border-danger text-danger" },
  error: { label: "Failing", symbol: "✕", className: "border-danger text-danger" },
};

const BEFORE_JUDGING = [
  "Warm the weather cache: python -m scripts.warm_cache (in backend/).",
  "Seed the returning homeowner at least 10 minutes before: python -m scripts.seed_demo.",
  "Open the demo browser, set its zoom, and check map tiles load on the SSCBS campus.",
  "Check the “Type the size instead” form opens on the roof step.",
  "Everything on this page is green and nothing is labelled mock.",
];

/** Pre-demo check: calls every external service once (/api/health?deep=true). */
export function StatusView() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(true);
  const [checkedAt, setCheckedAt] = useState<Date | null>(null);

  const check = useCallback(
    () =>
      api("get", "/api/health", { query: { deep: true }, timeoutMs: 60_000 })
        .then((h) => {
          setHealth(h);
          setError(null);
        })
        .catch((err) => {
          setHealth(null);
          setError(err instanceof ApiError ? err.message : "The check failed.");
        })
        .finally(() => {
          setChecking(false);
          setCheckedAt(new Date());
        }),
    [],
  );

  useEffect(() => {
    void check();
  }, [check]);

  const deps = health ? Object.entries(health.dependencies) : [];
  const allGreen =
    !!health && health.assumptions.complete && deps.every(([, d]) => d.status === "ok" && !d.is_mock);

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-8">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl">Demo readiness</h1>
          <p className="mt-1 text-muted-foreground">Calls each service once. Takes up to 30 seconds (the memory check is slow).</p>
        </div>
        <Button
          variant="secondary"
          disabled={checking}
          onClick={() => {
            setChecking(true);
            void check();
          }}
        >
          {checking ? "Checking…" : "Check again"}
        </Button>
      </header>

      {error && (
        <Card>
          <p role="alert" className="text-danger">
            {error}
          </p>
        </Card>
      )}

      {health && (
        <Card className="flex flex-col gap-4">
          <p className={cn("text-lg font-semibold", allGreen ? "text-success" : "text-danger")} role="status">
            {allGreen ? "✓ Ready: every service works and nothing is mocked." : "✕ Not ready: fix the items marked below."}
          </p>
          <ul className="flex flex-col divide-y divide-border" aria-label="Services">
            {deps.map(([key, d]) => {
              const state = STATE[d.status];
              return (
                <li key={key} className="flex flex-wrap items-center justify-between gap-2 py-2.5">
                  <div>
                    <p className="font-medium">{NAMES[key] ?? key}</p>
                    {d.detail && <p className="text-sm text-muted-foreground">{d.detail}</p>}
                  </div>
                  <div className="flex items-center gap-2">
                    {d.is_mock && <MockBadge />}
                    <span className={cn("whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium", state.className)}>
                      <span aria-hidden="true">{state.symbol} </span>
                      {state.label}
                    </span>
                  </div>
                </li>
              );
            })}
            <li className="flex flex-wrap items-center justify-between gap-2 py-2.5">
              <div>
                <p className="font-medium">Assumptions file ({health.assumptions.version})</p>
                {!health.assumptions.complete && (
                  <p className="text-sm text-muted-foreground">Missing: {health.assumptions.missing.join(", ")}</p>
                )}
              </div>
              <span
                className={cn(
                  "whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium",
                  health.assumptions.complete ? STATE.ok.className : STATE.error.className,
                )}
              >
                {health.assumptions.complete ? "✓ Complete" : "✕ Incomplete"}
              </span>
            </li>
          </ul>
          {checkedAt && (
            <p className="text-xs text-muted-foreground">
              Checked {checkedAt.toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata" })} · backend {health.version} (
              {health.app_env})
            </p>
          )}
        </Card>
      )}

      <Card>
        <h2 className="text-lg">Before judging</h2>
        <ol className="mt-2 flex list-decimal flex-col gap-1.5 pl-5 text-sm">
          {BEFORE_JUDGING.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ol>
      </Card>
    </div>
  );
}
