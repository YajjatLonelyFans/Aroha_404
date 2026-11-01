"use client";

import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";

export type ManualForm = { length: string; width: string; noGo: string[] };

export const EMPTY_MANUAL: ManualForm = { length: "", width: "", noGo: [] };

// Same limits as the backend's ManualDimensions (0 < size <= 200 m).
function checkSide(value: string, what: string): string | null {
  const n = Number(value);
  if (!value.trim() || !Number.isFinite(n) || n <= 0) return `Enter the roof's ${what} in metres.`;
  if (n > 200) return "That is larger than a house roof. Check the number.";
  return null;
}

function checkNoGo(value: string): string | null {
  const n = Number(value);
  return !value.trim() || !Number.isFinite(n) || n <= 0 ? "Enter the area in m², or remove this row." : null;
}

export function manualErrors(form: ManualForm) {
  return {
    length: checkSide(form.length, "length"),
    width: checkSide(form.width, "width"),
    noGo: form.noGo.map(checkNoGo),
  };
}

export function manualValid(form: ManualForm): boolean {
  const e = manualErrors(form);
  return !e.length && !e.width && e.noGo.every((x) => !x);
}

/** Fallback when the map can't be used: the roof as a rectangle, and no-go areas by size (PRD FR-3). */
export function ManualDimensionsForm({
  value,
  onChange,
  showErrors,
}: {
  value: ManualForm;
  onChange: (next: ManualForm) => void;
  showErrors: boolean;
}) {
  const errors = manualErrors(value);
  const setNoGo = (i: number, v: string) => onChange({ ...value, noGo: value.noGo.map((x, j) => (j === i ? v : x)) });
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-3">
        <Field
          label="Length (m)"
          type="number"
          inputMode="decimal"
          value={value.length}
          onChange={(e) => onChange({ ...value, length: e.target.value })}
          error={showErrors ? errors.length : null}
        />
        <Field
          label="Width (m)"
          type="number"
          inputMode="decimal"
          value={value.width}
          onChange={(e) => onChange({ ...value, width: e.target.value })}
          error={showErrors ? errors.width : null}
        />
      </div>
      <div className="flex flex-col gap-2">
        <p className="text-sm font-medium">No-go areas (water tank, stair room, heater)</p>
        {value.noGo.length === 0 && <p className="text-sm text-muted-foreground">None added.</p>}
        {value.noGo.map((v, i) => (
          <div key={i} className="flex items-end gap-2">
            <div className="flex-1">
              <Field
                label={`Area ${i + 1} (m²)`}
                type="number"
                inputMode="decimal"
                value={v}
                onChange={(e) => setNoGo(i, e.target.value)}
                error={showErrors ? errors.noGo[i] : null}
              />
            </div>
            <Button
              variant="ghost"
              className="mb-0.5"
              onClick={() => onChange({ ...value, noGo: value.noGo.filter((_, j) => j !== i) })}
              aria-label={`Remove area ${i + 1}`}
            >
              Remove
            </Button>
          </div>
        ))}
        <Button variant="secondary" className="self-start" onClick={() => onChange({ ...value, noGo: [...value.noGo, ""] })}>
          Add a no-go area
        </Button>
      </div>
      <p className="text-sm text-muted-foreground">
        Panel positions are not drawn for typed sizes, so the count is approximate
      </p>
    </div>
  );
}
