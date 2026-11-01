"use client";

import type { FeatureCollection } from "geojson";
import Link from "next/link";
import { useRef, useState } from "react";

import { Button, buttonClass } from "@/components/ui/button";
import type { LatLon } from "@/features/map/map-view";
import { ApiError, api, type Schemas } from "@/lib/api";
import { formatArea, formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

import { EMPTY_MANUAL, ManualDimensionsForm, manualValid, type ManualForm } from "./manual-dimensions";
import { DEFAULT_DETAILS, RoofDetailsForm, checkTilt, type Details } from "./roof-details";
import { RoofMap, type RoofMapHandle, type Tool } from "./roof-map";
import { RoofResult } from "./roof-result";
import { NO_GO_KINDS, areaM2, kindLabel, sideLengthsM, toSqFt, type Drawing, type NoGoKind, type Polygon } from "./roof-shapes";

type Step = "outline" | "nogo" | "details" | "result";
type Method = "map" | "manual";

const STEPS: { key: Step; label: string }[] = [
  { key: "outline", label: "Roof outline" },
  { key: "nogo", label: "No-go areas" },
  { key: "details", label: "Roof and shade" },
  { key: "result", label: "Panels" },
];

type Props = {
  userId: string;
  propertyId: string;
  pin: LatLon;
  config: Schemas["MapConfig"];
  savedRoof: Schemas["SavedRoof"] | null;
  savedResult: Schemas["RoofAssessResponse"] | null;
  /** Keeps the latest drawing and result if the person goes back to the pin and returns. */
  onAssessed: (inputs: Schemas["SavedRoof"], result: Schemas["RoofAssessResponse"]) => void;
  onBackToPin: () => void;
};

function detailsFrom(roof: Schemas["SavedRoof"] | null): Details {
  if (!roof) return DEFAULT_DETAILS;
  return {
    roofType: roof.roof_type,
    slopeTilt: roof.slope_tilt_deg == null ? "" : String(roof.slope_tilt_deg),
    slopeAzimuth: roof.slope_azimuth_deg ?? 0,
    shading: { ...DEFAULT_DETAILS.shading, ...roof.shading },
  };
}

function manualFrom(roof: Schemas["SavedRoof"] | null): ManualForm {
  const md = roof?.manual_dimensions;
  if (!md) return EMPTY_MANUAL;
  return { length: String(md.length_m), width: String(md.width_m), noGo: (md.no_go_areas_m2 ?? []).map(String) };
}

/** Steps 3–4 of the journey: trace the roof, mark no-go areas, answer roof and shade questions, see the panels. */
export function TraceRoof({ userId, propertyId, pin, config, savedRoof, savedResult, onAssessed, onBackToPin }: Props) {
  const mapRef = useRef<RoofMapHandle>(null);
  const [method, setMethod] = useState<Method>(savedRoof?.manual_dimensions ? "manual" : "map");
  const [step, setStep] = useState<Step>(savedResult ? "result" : "outline");
  // The saved drawing, loaded into the map once when it opens.
  const [initial] = useState(() => ({
    outline: (savedRoof?.outline as Polygon | null | undefined) ?? null,
    noGo: (savedRoof?.no_go_areas ?? []).map((n) => ({ kind: n.kind, geometry: n.geometry as unknown as Polygon })),
  }));
  // Start from the saved drawing too, so the steps work before the map has loaded; the map
  // replaces it (with its own shape ids) as soon as it is ready.
  const [drawing, setDrawing] = useState<Drawing>(() => ({
    outline: initial.outline,
    noGo: initial.noGo.map((n, i) => ({ id: `saved-${i}`, ...n })),
  }));
  const [drawingNoGo, setDrawingNoGo] = useState(false);
  const [noGoKind, setNoGoKind] = useState<NoGoKind>("water_tank");
  const [manual, setManual] = useState<ManualForm>(() => manualFrom(savedRoof));
  const [details, setDetails] = useState<Details>(() => detailsFrom(savedRoof));
  const [showErrors, setShowErrors] = useState(false);
  const [result, setResult] = useState(savedResult);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);


  const tool: Tool =
    method === "manual" || step === "details" || step === "result"
      ? "view"
      : step === "outline"
        ? drawing.outline
          ? "edit"
          : "draw-outline"
        : drawingNoGo
          ? "draw-nogo"
          : "edit";

  const go = (next: Step) => {
    setShowErrors(false);
    setError(null);
    setDrawingNoGo(false);
    setStep(next);
  };

  async function submit() {
    setShowErrors(true);
    if (checkTilt(details)) return;
    if (method === "manual" && !manualValid(manual)) return setStep("outline");
    if (method === "map" && !drawing.outline) return setStep("outline");
    setSubmitting(true);
    setError(null);
    const sloped = details.roofType === "sloped";
    const shape =
      method === "map"
        ? {
            outline: { ...drawing.outline! },
            no_go_areas: drawing.noGo.map((n) => ({ kind: n.kind, geometry: { ...n.geometry } })),
          }
        : {
            manual_dimensions: {
              length_m: Number(manual.length),
              width_m: Number(manual.width),
              no_go_areas_m2: manual.noGo.map(Number),
            },
          };
    const answers = {
      roof_type: details.roofType,
      slope_tilt_deg: sloped ? Number(details.slopeTilt) : null,
      slope_azimuth_deg: sloped ? details.slopeAzimuth : null,
      shading: details.shading,
    };
    try {
      const res = await api("post", "/api/roof/assess", {
        body: { user_id: userId, property_id: propertyId, ...answers, ...shape },
      });
      setResult(res);
      onAssessed({ ...answers, ...shape }, res);
      go("result");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  const outlineArea = drawing.outline ? areaM2(drawing.outline) : null;
  const showPanels = step === "result" && method === "map" && result?.panel_layout;

  return (
    <div className="mx-auto grid w-full max-w-6xl flex-1 gap-4 px-4 py-6 lg:grid-cols-[380px_1fr]">
      <div className="flex flex-col gap-5">
        <StepDots step={step} />

        {step === "outline" && method === "map" && (
          <Panel title="Trace your roof" intro="Click each corner of the roof. Click the first corner again to finish. Then drag corners to fine-tune.">
            <div className="rounded-md bg-muted p-3 text-sm tabular-nums">
              {outlineArea === null || !drawing.outline ? (
                "No outline yet."
              ) : (
                <>
                  <p>
                    Roof outline: about {formatArea(outlineArea)} ({formatNumber(toSqFt(outlineArea))} sq ft)
                  </p>
                  <p className="mt-1 text-muted-foreground">
                    Sides: {sideLengthsM(drawing.outline).map((m) => `${formatNumber(m, 1)} m`).join(", ")}
                  </p>
                  <p className="mt-1 text-muted-foreground">
                    Check these against your plot or the scale bar on the map. Trace only your own roof.
                  </p>
                </>
              )}
            </div>
            <div className="flex flex-wrap gap-3">
              <Button onClick={() => go("nogo")} disabled={!drawing.outline}>
                Next: no-go areas
              </Button>
              {drawing.outline && (
                <Button variant="ghost" onClick={() => mapRef.current?.clearOutline()}>
                  Start again
                </Button>
              )}
            </div>
            <LinkButton onClick={() => setMethod("manual")}>Can&apos;t trace it? Type the size instead</LinkButton>
          </Panel>
        )}

        {step === "outline" && method === "manual" && (
          <Panel title="Your roof's size" intro="Measure the open roof, or take it from the house plan.">
            <ManualDimensionsForm value={manual} onChange={setManual} showErrors={showErrors} />
            <Button
              onClick={() => {
                setShowErrors(true);
                if (manualValid(manual)) go("details");
              }}
            >
              Next: roof and shade
            </Button>
            <LinkButton onClick={() => setMethod("map")}>Trace it on the map instead</LinkButton>
          </Panel>
        )}

        {step === "nogo" && (
          <Panel
            title="Mark where panels can't go"
            intro="Water tanks, stair rooms and solar water heaters take roof space. Draw around each one."
          >
            <fieldset>
              <legend className="mb-2 text-sm font-medium">What are you marking?</legend>
              <div className="flex flex-wrap gap-2">
                {NO_GO_KINDS.map((k) => (
                  <label
                    key={k.value}
                    className={cn(
                      "cursor-pointer rounded-full border px-3 py-1 text-sm",
                      "has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-ring",
                      noGoKind === k.value ? "border-primary bg-primary text-primary-foreground" : "border-border hover:bg-muted",
                    )}
                  >
                    <input
                      type="radio"
                      name="nogo-kind"
                      className="sr-only"
                      checked={noGoKind === k.value}
                      onChange={() => setNoGoKind(k.value)}
                    />
                    {k.label}
                  </label>
                ))}
              </div>
            </fieldset>
            {drawingNoGo ? (
              <div className="flex flex-wrap items-center gap-3">
                <p className="text-sm">Click its corners on the map, then the first corner again.</p>
                <Button variant="ghost" onClick={() => setDrawingNoGo(false)}>
                  Cancel
                </Button>
              </div>
            ) : (
              <Button variant="secondary" className="self-start" onClick={() => setDrawingNoGo(true)}>
                Draw a {kindLabel(noGoKind).toLowerCase()}
              </Button>
            )}
            {drawing.noGo.length > 0 && (
              <ul className="flex flex-col gap-1 text-sm" aria-label="No-go areas">
                {drawing.noGo.map((n) => (
                  <li key={n.id} className="flex items-center justify-between rounded-md bg-muted px-3 py-1.5 tabular-nums">
                    <span>
                      {kindLabel(n.kind)}, about {formatArea(areaM2(n.geometry))}
                    </span>
                    <button
                      type="button"
                      onClick={() => mapRef.current?.removeNoGo(n.id)}
                      className="text-sm font-medium text-primary hover:underline"
                    >
                      Remove
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <div className="flex flex-wrap gap-3">
              <Button onClick={() => go("details")} disabled={drawingNoGo}>
                {drawing.noGo.length ? "Next: roof and shade" : "Nothing to mark: next"}
              </Button>
              <Button variant="ghost" onClick={() => go("outline")}>
                Back
              </Button>
            </div>
          </Panel>
        )}

        {step === "details" && (
          <Panel title="A few questions about the roof">
            <RoofDetailsForm value={details} onChange={setDetails} showErrors={showErrors} />
            {error && (
              <p role="alert" className="rounded-md border border-danger px-3 py-2 text-sm text-danger">
                {error}
              </p>
            )}
            <div className="flex flex-wrap gap-3">
              <Button onClick={submit} disabled={submitting}>
                {submitting ? "Working it out…" : "Work out my panels"}
              </Button>
              <Button variant="ghost" onClick={() => go(method === "map" ? "nogo" : "outline")} disabled={submitting}>
                Back
              </Button>
            </div>
          </Panel>
        )}

        {step === "result" && result && (
          <>
            <RoofResult result={result} />
            <div className="flex flex-col gap-2">
              <Link href="/results" className={buttonClass("primary")}>
                See my savings estimate
              </Link>
              <Button variant="ghost" onClick={() => go("outline")}>
                Change the roof drawing
              </Button>
              <Button variant="ghost" onClick={() => go("details")}>
                Change roof type or shade
              </Button>
            </div>
          </>
        )}

        {step !== "result" && (
          <LinkButton onClick={onBackToPin}>Back to the map pin</LinkButton>
        )}
      </div>

      <div className="h-[60vh] lg:h-auto lg:min-h-[600px]">
        <RoofMap
          ref={mapRef}
          config={config}
          center={pin}
          initial={initial}
          tool={tool}
          noGoKind={noGoKind}
          panels={showPanels ? (result!.panel_layout as unknown as FeatureCollection) : null}
          onChange={setDrawing}
          onFinish={(what) => {
            if (what === "nogo") setDrawingNoGo(false);
          }}
        />
      </div>
    </div>
  );
}

function Panel({ title, intro, children }: { title: string; intro?: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl">{title}</h1>
        {intro && <p className="mt-2 text-muted-foreground">{intro}</p>}
      </div>
      {children}
    </section>
  );
}

function StepDots({ step }: { step: Step }) {
  const index = STEPS.findIndex((s) => s.key === step);
  return (
    <p className="text-sm text-muted-foreground">
      Step {index + 1} of {STEPS.length}: {STEPS[index].label}
    </p>
  );
}

function LinkButton({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" onClick={onClick} className="self-start text-sm font-medium text-primary hover:underline">
      {children}
    </button>
  );
}
