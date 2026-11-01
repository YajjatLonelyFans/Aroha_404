"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { ApiError, api } from "@/lib/api";
import { cn } from "@/lib/utils";

import {
  DISCOM_OPTIONS,
  PROPERTY_OPTIONS,
  ROOF_OPTIONS,
  STEPS,
  stepError,
  toRequest,
  type Answers,
  type Option,
} from "./questions";

type Props = {
  displayName: string;
  initial: Answers;
  onSubmitted: (userId: string) => void;
  onCancel?: () => void;
};

/** Four qualifying questions, one at a time, with progress dots (DESIGN_SYSTEM "Qualify card"). */
export function QualifyCard({ displayName, initial, onSubmitted, onCancel }: Props) {
  const [answers, setAnswers] = useState<Answers>(initial);
  const [index, setIndex] = useState(0);
  const [showError, setShowError] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const moved = useRef(false);

  const step = STEPS[index];
  const isLast = index === STEPS.length - 1;
  const error = stepError(step, answers);

  // Move keyboard and screen-reader focus to the new question (not on first render).
  useEffect(() => {
    if (moved.current) headingRef.current?.focus();
  }, [index]);

  function go(to: number) {
    moved.current = true;
    setShowError(false);
    setFailure(null);
    setIndex(to);
  }

  async function next(e: FormEvent) {
    e.preventDefault();
    if (error) return setShowError(true);
    if (!isLast) return go(index + 1);
    const body = toRequest(answers, displayName);
    if (!body) return setShowError(true);
    setSubmitting(true);
    setFailure(null);
    try {
      const res = await api("post", "/api/users", { body });
      onSubmitted(res.user_id);
    } catch (err) {
      setFailure(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
      setSubmitting(false);
    }
  }

  const set = <K extends keyof Answers>(key: K, value: Answers[K]) => {
    setAnswers((a) => ({ ...a, [key]: value }));
    setShowError(false);
  };

  return (
    <Card className="w-full max-w-xl">
      <ProgressDots current={index} total={STEPS.length} />
      <form onSubmit={next} noValidate className="mt-6">
        <fieldset aria-describedby="qualify-help">
          <legend className="contents">
            <span className="text-sm text-muted-foreground">
              Question {index + 1} of {STEPS.length}
            </span>
            <h1 ref={headingRef} tabIndex={-1} className="mt-1 text-2xl outline-none">
              {step.title}
            </h1>
          </legend>
          <p id="qualify-help" className="mt-2 text-muted-foreground">
            {step.help}
          </p>

          <div className="mt-6">
            {step.key === "property_type" && (
              <Choices name="property_type" options={PROPERTY_OPTIONS} value={answers.property_type} onChange={(v) => set("property_type", v)} />
            )}
            {step.key === "has_roof_rights" && (
              <Choices name="has_roof_rights" options={ROOF_OPTIONS} value={answers.has_roof_rights} onChange={(v) => set("has_roof_rights", v)} />
            )}
            {step.key === "monthly_units_kwh" && (
              <Field
                label="Units per month"
                type="number"
                inputMode="decimal"
                min={1}
                max={20000}
                value={answers.monthly_units_kwh}
                onChange={(e) => set("monthly_units_kwh", e.target.value)}
                error={showError ? error : null}
                hint="Look for “units consumed” or “kWh” on your bill."
              />
            )}
            {step.key === "discom" && (
              <Choices name="discom" options={DISCOM_OPTIONS} value={answers.discom} onChange={(v) => set("discom", v)} />
            )}
          </div>
          {showError && error && step.key !== "monthly_units_kwh" && (
            <p role="alert" className="mt-3 text-sm text-danger">
              {error}
            </p>
          )}
        </fieldset>

        {failure && (
          <p role="alert" className="mt-4 rounded-md border border-danger px-3 py-2 text-sm text-danger">
            {failure}
          </p>
        )}

        <div className="mt-8 flex items-center justify-between gap-3">
          {index > 0 ? (
            <Button variant="ghost" onClick={() => go(index - 1)} disabled={submitting}>
              Back
            </Button>
          ) : onCancel ? (
            <Button variant="ghost" onClick={onCancel}>
              Cancel
            </Button>
          ) : (
            <span />
          )}
          <Button type="submit" disabled={submitting}>
            {isLast ? (submitting ? "Checking…" : "Check my home") : "Next"}
          </Button>
        </div>
      </form>
    </Card>
  );
}

function ProgressDots({ current, total }: { current: number; total: number }) {
  return (
    <div className="flex items-center gap-2" aria-hidden="true">
      {Array.from({ length: total }, (_, i) => (
        <span
          key={i}
          className={cn(
            "h-2.5 rounded-full transition-all",
            i === current ? "w-6 bg-primary" : i < current ? "w-2.5 bg-accent" : "w-2.5 bg-border",
          )}
        />
      ))}
    </div>
  );
}

function Choices<V extends string>({
  name,
  options,
  value,
  onChange,
}: {
  name: string;
  options: Option<V>[];
  value: V | undefined;
  onChange: (value: V) => void;
}) {
  return (
    <div className="flex flex-col gap-3">
      {options.map((o) => {
        const checked = value === o.value;
        return (
          <label
            key={o.value}
            className={cn(
              "flex cursor-pointer items-start gap-3 rounded-md border p-4 transition-colors",
              "has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-ring",
              checked ? "border-primary bg-primary/5" : "border-border hover:bg-muted",
            )}
          >
            <input
              type="radio"
              name={name}
              value={o.value}
              checked={checked}
              onChange={() => onChange(o.value)}
              className="mt-1 size-4 accent-primary"
            />
            <span>
              <span className="block font-medium">{o.label}</span>
              {o.hint && <span className="block text-sm text-muted-foreground">{o.hint}</span>}
            </span>
          </label>
        );
      })}
    </div>
  );
}
