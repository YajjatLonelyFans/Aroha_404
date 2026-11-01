"use client";

import { Field } from "@/components/ui/field";
import { cn } from "@/lib/utils";

import { FACINGS, SHADE_LEVELS, SIDES, type ShadeLevel, type Side } from "./roof-shapes";

export type Details = {
  roofType: "flat" | "sloped";
  slopeTilt: string; // degrees, as typed
  slopeAzimuth: number; // 0 = south
  shading: Record<Side, ShadeLevel>;
};

export const DEFAULT_DETAILS: Details = {
  roofType: "flat",
  slopeTilt: "",
  slopeAzimuth: 0,
  shading: { east: "none", south: "none", west: "none", north: "none" },
};

export function checkTilt(details: Details): string | null {
  if (details.roofType !== "sloped") return null;
  const n = Number(details.slopeTilt);
  if (!details.slopeTilt.trim() || !Number.isFinite(n) || n <= 0 || n >= 90) return "Enter the roof's slope in degrees (1–89).";
  return null;
}

/** Roof type and shade by side (PRD FR-5). */
export function RoofDetailsForm({
  value,
  onChange,
  showErrors,
}: {
  value: Details;
  onChange: (next: Details) => void;
  showErrors: boolean;
}) {
  const set = (patch: Partial<Details>) => onChange({ ...value, ...patch });
  return (
    <div className="flex flex-col gap-6">
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-2 font-medium">Is the roof flat or sloped?</legend>
        <Segmented
          name="roof-type"
          options={[
            { value: "flat", label: "Flat" },
            { value: "sloped", label: "Sloped" },
          ]}
          value={value.roofType}
          onChange={(roofType) => set({ roofType })}
        />
        <p className="text-sm text-muted-foreground">
          {value.roofType === "flat"
            ? "Panels go on frames tilted towards the south."
            : "Panels lie flat on the slope, facing the way it faces."}
        </p>
      </fieldset>

      {value.roofType === "sloped" && (
        <div className="grid grid-cols-2 gap-3">
          <Field
            label="Slope (degrees)"
            type="number"
            inputMode="decimal"
            min={1}
            max={89}
            value={value.slopeTilt}
            onChange={(e) => set({ slopeTilt: e.target.value })}
            error={showErrors ? checkTilt(value) : null}
          />
          <div className="flex flex-col gap-1.5">
            <label htmlFor="slope-facing" className="text-sm font-medium">
              Faces
            </label>
            <select
              id="slope-facing"
              value={value.slopeAzimuth}
              onChange={(e) => set({ slopeAzimuth: Number(e.target.value) })}
              className="h-11 rounded-md border border-border bg-card px-3"
            >
              {FACINGS.map((f) => (
                <option key={f.azimuth} value={f.azimuth}>
                  {f.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      )}

      <fieldset>
        <legend className="font-medium">Do taller buildings or trees shade the roof?</legend>
        <p className="mt-1 text-sm text-muted-foreground">Think about each side of the house during the day.</p>
        <div className="mt-3 flex flex-col gap-3">
          {SIDES.map((side) => (
            <div key={side.value} className="flex flex-wrap items-center justify-between gap-2">
              <span id={`shade-${side.value}`} className="text-sm">
                {side.label}
              </span>
              <Segmented
                name={`shade-${side.value}`}
                labelledBy={`shade-${side.value}`}
                options={SHADE_LEVELS}
                value={value.shading[side.value]}
                onChange={(level) => set({ shading: { ...value.shading, [side.value]: level } })}
                small
              />
            </div>
          ))}
        </div>
      </fieldset>
    </div>
  );
}

function Segmented<V extends string>({
  name,
  options,
  value,
  onChange,
  labelledBy,
  small,
}: {
  name: string;
  options: { value: V; label: string }[];
  value: V;
  onChange: (value: V) => void;
  labelledBy?: string;
  small?: boolean;
}) {
  return (
    <div role="radiogroup" aria-labelledby={labelledBy} className="inline-flex rounded-md border border-border bg-card p-0.5">
      {options.map((o) => (
        <label
          key={o.value}
          className={cn(
            "cursor-pointer rounded px-3 font-medium transition-colors",
            "has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-ring",
            small ? "py-1 text-xs" : "py-2 text-sm",
            value === o.value ? "bg-primary text-primary-foreground" : "text-foreground hover:bg-muted",
          )}
        >
          <input
            type="radio"
            name={name}
            value={o.value}
            checked={value === o.value}
            onChange={() => onChange(o.value)}
            className="sr-only"
          />
          {o.label}
        </label>
      ))}
    </div>
  );
}
