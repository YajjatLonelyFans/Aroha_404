"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { MockBadge } from "@/components/mock-badge";
import { Button, buttonClass } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { OutlookCard } from "@/features/weather/outlook-card";
import { ApiError, api, type Schemas } from "@/lib/api";
import { formatDateTime, formatKwh, formatKwhRange, formatKwp, formatKwpNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

import { FinanceTable } from "./finance-table";
import { GenerationChart } from "./generation-chart";

type Estimate = Schemas["SolarEstimateResponse"];
type Load =
  | { kind: "loading"; message: string }
  | { kind: "error"; message: string }
  | { kind: "no-roof" }
  | {
      kind: "ready";
      estimate: Estimate;
      assessment: Schemas["RoofAssessResponse"];
      pin: { lat: number; lon: number };
    };

const message = (err: unknown) => (err instanceof ApiError ? err.message : "Something went wrong.");

const BINDING: Record<Estimate["binding_constraint"], string> = {
  roof: "Limited by your roof",
  consumption: "Sized to your electricity use",
  limit: "Capped at the allowed size",
  minimum: "Smallest practical size",
};

/** Step 5: generation, cost, subsidy, savings and payback for the traced roof (PRD FR-11 to FR-16). */
export function ResultsView({ userId }: { userId: string }) {
  const [load, setLoad] = useState<Load>({ kind: "loading", message: "Loading your estimate…" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const ctrl = new AbortController();
    const { signal } = ctrl;
    (async () => {
      const user = await api("get", "/api/users/{user_id}", { path: { user_id: userId }, signal });
      const assessmentId = user.latest.assessment_id;
      if (!assessmentId) return setLoad({ kind: "no-roof" });
      const assessment = await api("get", "/api/roof/assessments/{assessment_id}", {
        path: { assessment_id: assessmentId },
        signal,
      });
      const property = await api("get", "/api/properties/{property_id}", {
        path: { property_id: assessment.property_id },
        signal,
      });
      // Reuse the saved estimate if it was made for this roof; otherwise work out a new one.
      let estimate: Estimate | null = null;
      if (user.latest.estimate_id) {
        const saved = await api("get", "/api/solar/estimates/{estimate_id}", {
          path: { estimate_id: user.latest.estimate_id },
          signal,
        });
        if (saved.assessment_id === assessmentId) estimate = saved;
      }
      if (!estimate) {
        setLoad({ kind: "loading", message: "Working out your estimate from 10 years of weather… this can take a few seconds." });
        estimate = await api("post", "/api/solar/estimate", {
          body: { user_id: userId, assessment_id: assessmentId },
          signal,
          timeoutMs: 60_000,
        });
      }
      setLoad({ kind: "ready", estimate, assessment, pin: { lat: property.lat, lon: property.lon } });
    })().catch((err) => {
      if (!signal.aborted) setLoad({ kind: "error", message: message(err) });
    });
    return () => ctrl.abort();
  }, [userId, attempt]);

  if (load.kind === "loading") return <p className="p-6 text-muted-foreground">{load.message}</p>;
  if (load.kind === "error") {
    return (
      <Card className="m-auto w-full max-w-md">
        <p role="alert" className="text-danger">
          {load.message}
        </p>
        <Button
          className="mt-4"
          onClick={() => {
            setLoad({ kind: "loading", message: "Loading your estimate…" });
            setAttempt((n) => n + 1);
          }}
        >
          Try again
        </Button>
      </Card>
    );
  }
  if (load.kind === "no-roof") {
    return (
      <Card className="m-auto w-full max-w-md">
        <h1 className="text-2xl">Trace your roof first</h1>
        <p className="mt-2 text-muted-foreground">The estimate is worked out from your roof and its panels.</p>
        <Link href="/roof" className={buttonClass("primary", "mt-6")}>
          Go to my roof
        </Link>
      </Card>
    );
  }
  return <Results estimate={load.estimate} assessment={load.assessment} pin={load.pin} />;
}

function Results({
  estimate,
  assessment,
  pin,
}: {
  estimate: Estimate;
  assessment: Schemas["RoofAssessResponse"];
  pin: { lat: number; lon: number };
}) {
  const recommendedIndex = Math.max(0, estimate.options.findIndex((o) => o.recommended));
  const [selected, setSelected] = useState(recommendedIndex);
  const option = estimate.options[selected];
  const recommended = estimate.options[recommendedIndex];
  const [climate, setClimate] = useState<Schemas["ClimatologyResponse"] | null>(null);
  const [forecast, setForecast] = useState<Schemas["ForecastResponse"] | null>(null);
  const [forecastError, setForecastError] = useState<string | null>(null);

  // Season bands and notes, and the 7-day outlook. Neither blocks the estimate.
  useEffect(() => {
    const ctrl = new AbortController();
    const query = { lat: pin.lat, lon: pin.lon, tilt: assessment.array_tilt_deg, azimuth: assessment.array_azimuth_deg };
    api("get", "/api/weather/climatology", { query, signal: ctrl.signal, timeoutMs: 60_000 })
      .then(setClimate)
      .catch(() => {});
    api("get", "/api/weather/forecast", { query, signal: ctrl.signal })
      .then(setForecast)
      .catch((err) => {
        if (!ctrl.signal.aborted) setForecastError(message(err));
      });
    return () => ctrl.abort();
  }, [pin.lat, pin.lon, assessment.array_tilt_deg, assessment.array_azimuth_deg]);

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-4 py-8">
      <header className="flex flex-col gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-3xl">Your solar estimate</h1>
            {estimate.is_mock && <MockBadge what="weather" />}
          </div>
          <p className="mt-2 text-muted-foreground tabular-nums">
            <span className="font-medium text-foreground">{BINDING[estimate.binding_constraint]}</span> · Roof fits up to{" "}
            {formatKwp(estimate.roof_kwp)}; your use needs about {formatKwp(estimate.consumption_kwp)}
          </p>
        </div>
        <div className="grid gap-4 sm:grid-cols-[3fr_2fr]">
          <Stat lead label="Recommended size" value={formatKwp(estimate.recommended_kwp)} note={`${recommended.panel_count} panels`} />
          <Stat
            label="Typical year"
            value={formatKwh(recommended.annual_kwh.median)}
            note={`Range ${formatKwhRange(recommended.annual_kwh.p10, recommended.annual_kwh.p90)}`}
          />
        </div>
      </header>

      <Card className="flex flex-col gap-4">
        {estimate.options.length > 1 && (
          <div role="tablist" aria-label="System size" className="inline-flex max-w-full self-start overflow-x-auto rounded-md border border-border p-0.5">
            {estimate.options.map((o, i) => (
              <button
                key={o.capacity_kwp}
                role="tab"
                type="button"
                aria-selected={i === selected}
                onClick={() => setSelected(i)}
                className={cn(
                  "whitespace-nowrap rounded px-3 py-1.5 text-sm font-medium tabular-nums",
                  i === selected ? "bg-primary text-primary-foreground" : "hover:bg-muted",
                )}
              >
                {formatKwpNumber(o.capacity_kwp)} kWp{o.recommended ? " (recommended)" : ""}
              </button>
            ))}
          </div>
        )}
        <GenerationChart option={option} seasons={climate?.seasons ?? null} period={climate?.period ?? null} />
        {climate && climate.season_notes.length > 0 && (
          <div>
            <h3 className="text-base">How the seasons change it</h3>
            <ul className="mt-2 flex list-disc flex-col gap-1 pl-5 text-sm">
              {climate.season_notes.map((n) => (
                <li key={n.season + n.statement}>{n.statement}</li>
              ))}
            </ul>
          </div>
        )}
      </Card>

      <Card className="flex flex-col gap-3">
        <h2 className="text-xl">Cost, subsidy and savings</h2>
        <FinanceTable options={estimate.options} />
      </Card>

      <OutlookCard forecast={forecast} error={forecastError} />

      <section className="flex flex-col gap-2 text-sm text-muted-foreground">
        <p className="font-medium text-foreground">{estimate.disclaimer}</p>
        {estimate.notes.length > 0 && (
          <ul className="flex list-disc flex-col gap-1 pl-5">
            {estimate.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        )}
        <details>
          <summary className="cursor-pointer font-medium text-primary">Assumptions and sources</summary>
          <ul className="mt-2 flex list-disc flex-col gap-1 pl-5">
            {estimate.assumptions.map((a) => (
              <li key={a}>{a}</li>
            ))}
            {estimate.sources.map((s) => (
              <li key={s.name}>
                {s.url ? (
                  <a href={s.url} target="_blank" rel="noreferrer" className="text-primary underline">
                    {s.name}
                  </a>
                ) : (
                  s.name
                )}
                , retrieved {formatDateTime(s.retrieved_at)}
                {s.note ? `. ${s.note}` : ""}
              </li>
            ))}
            <li>
              Assumptions {estimate.assumptions_version}, model {estimate.model_version}.
            </li>
          </ul>
        </details>
      </section>

      <div className="flex flex-wrap items-center gap-3">
        <Link href="/journey" className={buttonClass("primary")}>
          Check my subsidies and next steps
        </Link>
        <Link href="/roof" className={buttonClass("ghost")}>
          Back to my roof
        </Link>
      </div>
    </div>
  );
}

function Stat({ label, value, note, lead }: { label: string; value: string; note: string; lead?: boolean }) {
  return (
    <div className="rounded-lg border border-border bg-card p-5">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className={cn("mt-1 font-heading font-semibold tabular-nums text-primary", lead ? "text-4xl" : "text-2xl")}>{value}</p>
      <p className="mt-1 text-sm text-muted-foreground tabular-nums">{note}</p>
    </div>
  );
}
