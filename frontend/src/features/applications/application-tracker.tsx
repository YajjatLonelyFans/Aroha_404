"use client";

import { useState } from "react";

import { ApiError, api, type Schemas } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

type Application = Schemas["ApplicationResponse"];
type Stage = Application["status"];
type StepStatus = Schemas["StepOut"]["status"];

const STAGES: { value: Stage; label: string }[] = [
  { value: "planning", label: "Planning" },
  { value: "applied", label: "Applied" },
  { value: "inspection", label: "Inspection" },
  { value: "commissioned", label: "Switched on" },
];

const ACTOR: Record<string, string> = { homeowner: "You", discom: "Your DISCOM", vendor: "Your installer" };

const STEP_STATUS: { value: StepStatus; label: string }[] = [
  { value: "todo", label: "To do" },
  { value: "doing", label: "In progress" },
  { value: "done", label: "Done" },
];

/** Steps, progress and the document checklist for the homeowner's DISCOM (PRD FR-19, FR-20). Saved as you go. */
export function ApplicationTracker({ initial, userId }: { initial: Application; userId: string }) {
  const [app, setApp] = useState(initial);
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function update(key: string, change: { step_id: string; step_status: StepStatus } | { document_type: string; provided: boolean }) {
    setSaving(key);
    setError(null);
    try {
      setApp(
        await api("patch", "/api/applications/{application_id}", {
          path: { application_id: app.application_id },
          body: { user_id: userId, ...change },
        }),
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save that. Try again.");
    } finally {
      setSaving(null);
    }
  }

  const stageIndex = STAGES.findIndex((s) => s.value === app.status);
  const done = app.steps.filter((s) => s.status === "done").length;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <ol className="grid grid-cols-4 gap-1" aria-label="Application progress">
          {STAGES.map((s, i) => (
            <li key={s.value} className="flex flex-col gap-1.5">
              <span className={cn("h-2 rounded-full", i <= stageIndex ? "bg-primary" : "bg-border")} />
              <span className={cn("text-xs", i === stageIndex ? "font-semibold text-primary" : "text-muted-foreground")}>
                {s.label}
                {i === stageIndex && <span className="sr-only"> (current stage)</span>}
              </span>
            </li>
          ))}
        </ol>
        <p className="mt-2 text-sm text-muted-foreground tabular-nums">
          {done} of {app.steps.length} steps done
        </p>
      </div>

      {app.next_actions.length > 0 && (
        <div className="rounded-md bg-muted p-4">
          <h3 className="text-base">What to do next</h3>
          <ol className="mt-2 flex list-decimal flex-col gap-1 pl-5 text-sm">
            {app.next_actions.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ol>
        </div>
      )}

      {error && (
        <p role="alert" className="rounded-md border border-danger px-3 py-2 text-sm text-danger">
          {error}
        </p>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <section aria-labelledby="steps-title">
          <h3 id="steps-title" className="text-lg">
            Steps
          </h3>
          {STAGES.map((stage) => {
            const steps = app.steps.filter((s) => s.stage === stage.value);
            if (!steps.length) return null;
            return (
              <div key={stage.value} className="mt-4">
                <h4 className="text-sm font-semibold text-muted-foreground">{stage.label}</h4>
                <ul className="mt-2 flex flex-col gap-2">
                  {steps.map((step) => (
                    <li
                      key={step.id}
                      className={cn(
                        "flex flex-col gap-2 rounded-md border border-border bg-card p-3 sm:flex-row sm:items-center sm:justify-between",
                        step.status === "done" && "bg-muted",
                      )}
                    >
                      <div className="text-sm">
                        <p className={cn(step.status === "done" && "text-muted-foreground line-through")}>{step.title}</p>
                        <p className="mt-0.5 text-xs text-muted-foreground">
                          {ACTOR[step.actor] ?? step.actor}
                          {step.updated_at ? ` · updated ${formatDate(step.updated_at)}` : ""}
                        </p>
                      </div>
                      <label className="sr-only" htmlFor={`step-${step.id}`}>
                        Status of: {step.title}
                      </label>
                      <select
                        id={`step-${step.id}`}
                        value={step.status}
                        disabled={saving !== null}
                        onChange={(e) => update(`step-${step.id}`, { step_id: step.id, step_status: e.target.value as StepStatus })}
                        className="h-9 shrink-0 rounded-md border border-border bg-card px-2 text-sm"
                      >
                        {STEP_STATUS.map((o) => (
                          <option key={o.value} value={o.value}>
                            {o.label}
                          </option>
                        ))}
                      </select>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </section>

        <section aria-labelledby="docs-title" className="flex flex-col gap-3">
          <h3 id="docs-title" className="text-lg">
            Documents
          </h3>
          <p className="text-sm text-muted-foreground">
            {app.missing_documents.length
              ? `${app.missing_documents.length} required still to get ready.`
              : "All required documents are ready."}
          </p>
          <ul className="flex flex-col gap-2">
            {app.documents.map((d) => (
              <li key={d.type} className="rounded-md border border-border bg-card p-3 text-sm">
                <label className="flex cursor-pointer items-start gap-3">
                  <input
                    type="checkbox"
                    checked={d.provided}
                    disabled={saving !== null}
                    onChange={(e) => update(`doc-${d.type}`, { document_type: d.type, provided: e.target.checked })}
                    className="mt-0.5 size-4 accent-primary"
                  />
                  <span>
                    <span className="block">{d.label}</span>
                    <span className="block text-xs text-muted-foreground">
                      {d.required ? "Required" : "Optional"}
                      {d.verified ? "" : " · not yet confirmed on an official page"}
                    </span>
                  </span>
                </label>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <p className="text-xs text-muted-foreground">
        {app.note} Steps for {app.discom} from the{" "}
        <a href={app.source_url} target="_blank" rel="noreferrer" className="font-medium text-primary underline">
          official procedure
        </a>
        , verified on {formatDate(app.verified_on)}.
      </p>
    </div>
  );
}
