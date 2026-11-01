"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Button, buttonClass } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { AddressSearch } from "@/features/map/address-search";
import { MapView, type LatLon } from "@/features/map/map-view";
import { ApiError, api, type Schemas } from "@/lib/api";

import { TraceRoof } from "./trace-roof";

type Saved = { propertyId: string; pin: LatLon; address: string | null };
type Roof = { inputs: Schemas["SavedRoof"]; result: Schemas["RoofAssessResponse"] | null };
type Load =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | {
      kind: "ready";
      config: Schemas["MapConfig"];
      user: Schemas["UserSummary"];
      saved: Saved | null;
      roof: Roof | null;
    };

const message = (err: unknown) => (err instanceof ApiError ? err.message : "Something went wrong.");

/**
 * Steps 2–4 of the journey: pin the house (PRD FR-2), then trace the roof (FR-3 to FR-6).
 * A saved pin, drawing and panel result are shown again on return.
 */
export function LocateHouse({ userId }: { userId: string }) {
  const [load, setLoad] = useState<Load>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const ctrl = new AbortController();
    const { signal } = ctrl;
    (async () => {
      const [config, user] = await Promise.all([
        api("get", "/api/map/config", { signal }),
        api("get", "/api/users/{user_id}", { path: { user_id: userId }, signal }),
      ]);
      let saved: Saved | null = null;
      let roof: Roof | null = null;
      if (user.latest.property_id) {
        const p = await api("get", "/api/properties/{property_id}", {
          path: { property_id: user.latest.property_id },
          signal,
        });
        saved = { propertyId: p.property_id, pin: { lat: p.lat, lon: p.lon }, address: p.address_text ?? null };
        if (p.roof) {
          let result: Schemas["RoofAssessResponse"] | null = null;
          if (user.latest.assessment_id) {
            const a = await api("get", "/api/roof/assessments/{assessment_id}", {
              path: { assessment_id: user.latest.assessment_id },
              signal,
            });
            if (a.property_id === p.property_id) result = a; // only a result for this pin counts
          }
          roof = { inputs: p.roof, result };
        }
      }
      setLoad({ kind: "ready", config, user, saved, roof });
    })().catch((err) => {
      if (!signal.aborted) setLoad({ kind: "error", message: message(err) });
    });
    return () => ctrl.abort();
  }, [userId, attempt]);

  if (load.kind === "loading") {
    return <p className="p-6 text-muted-foreground">Loading the map…</p>;
  }
  if (load.kind === "error") {
    return (
      <Card className="m-auto w-full max-w-md">
        <p role="alert" className="text-danger">
          {load.message}
        </p>
        <Button
          className="mt-4"
          onClick={() => {
            setLoad({ kind: "loading" });
            setAttempt((n) => n + 1);
          }}
        >
          Try again
        </Button>
      </Card>
    );
  }
  if (!load.user.eligible_to_continue) {
    return (
      <Card className="m-auto w-full max-w-md">
        <h1 className="text-2xl">This home can&apos;t go on yet</h1>
        <p className="mt-2">{load.user.reason}</p>
        <Link href="/start" className={buttonClass("primary", "mt-6")}>
          Review my answers
        </Link>
      </Card>
    );
  }
  return <RoofJourney userId={userId} config={load.config} initialPin={load.saved} initialRoof={load.roof} />;
}

function RoofJourney({
  userId,
  config,
  initialPin,
  initialRoof,
}: {
  userId: string;
  config: Schemas["MapConfig"];
  initialPin: Saved | null;
  initialRoof: Roof | null;
}) {
  const [pin, setPin] = useState(initialPin);
  const [roof, setRoof] = useState(initialRoof);
  const [stage, setStage] = useState<"pin" | "roof">(initialPin && initialRoof?.result ? "roof" : "pin");

  if (stage === "roof" && pin) {
    return (
      <TraceRoof
        key={pin.propertyId}
        userId={userId}
        propertyId={pin.propertyId}
        pin={pin.pin}
        config={config}
        savedRoof={roof?.inputs ?? null}
        savedResult={roof?.result ?? null}
        onAssessed={(inputs, result) => setRoof({ inputs, result })}
        onBackToPin={() => setStage("pin")}
      />
    );
  }
  return (
    <PinStep
      userId={userId}
      config={config}
      initial={pin}
      onSaved={(next) => {
        setPin(next);
        setRoof(null); // a new pin is a new property: its roof has not been drawn yet
      }}
      onTrace={() => setStage("roof")}
    />
  );
}

function PinStep({
  userId,
  config,
  initial,
  onSaved,
  onTrace,
}: {
  userId: string;
  config: Schemas["MapConfig"];
  initial: Saved | null;
  onSaved: (saved: Saved) => void;
  onTrace: () => void;
}) {
  const [saved, setSaved] = useState<Saved | null>(initial);
  const [editing, setEditing] = useState(initial === null);
  const [pin, setPin] = useState<LatLon | null>(initial?.pin ?? null);
  const [address, setAddress] = useState<string | null>(initial?.address ?? null);
  const [focusKey, setFocusKey] = useState(initial ? 1 : 0);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const movePin = useCallback((next: LatLon) => {
    setPin(next);
    setSaveError(null);
  }, []);

  async function save() {
    if (!pin) return;
    setSaving(true);
    setSaveError(null);
    try {
      const res = await api("post", "/api/properties", {
        body: { user_id: userId, lat: pin.lat, lon: pin.lon, address_text: address },
      });
      const next = { propertyId: res.property_id, pin, address };
      setSaved(next);
      onSaved(next);
      setEditing(false);
    } catch (err) {
      setSaveError(message(err));
    } finally {
      setSaving(false);
    }
  }

  function cancelEdit() {
    if (!saved) return;
    setPin(saved.pin);
    setAddress(saved.address);
    setSaveError(null);
    setEditing(false);
    setFocusKey((k) => k + 1);
  }

  return (
    <div className="mx-auto grid w-full max-w-6xl flex-1 gap-4 px-4 py-6 lg:grid-cols-[360px_1fr]">
      <div className="flex flex-col gap-5">
        <div>
          <h1 className="text-2xl">Find your house</h1>
          <p className="mt-2 text-muted-foreground">
            {editing
              ? "Search for your address, then click on your roof to drop the pin. Drag the pin to adjust it."
              : "Your house is pinned. Next, you will trace the outline of the roof."}
          </p>
        </div>

        {editing && (
          <AddressSearch
            onPick={(place) => {
              movePin({ lat: place.lat, lon: place.lon });
              setAddress(place.display_name);
              setFocusKey((k) => k + 1);
            }}
          />
        )}

        <div className="rounded-md bg-muted p-4 text-sm">
          {pin ? (
            <>
              <p className="font-medium">{saved && !editing ? "Pin saved" : "Pin placed"}</p>
              {address && <p className="mt-1 text-muted-foreground">{address}</p>}
              <p className="mt-1 tabular-nums text-muted-foreground">
                {pin.lat.toFixed(5)}, {pin.lon.toFixed(5)}
              </p>
            </>
          ) : (
            <p className="text-muted-foreground">No pin yet. Click on your roof in the map.</p>
          )}
        </div>

        {saveError && (
          <p role="alert" className="rounded-md border border-danger px-3 py-2 text-sm text-danger">
            {saveError}
          </p>
        )}

        {editing ? (
          <div className="flex flex-wrap gap-3">
            <Button onClick={save} disabled={!pin || saving}>
              {saving ? "Saving…" : "Use this location"}
            </Button>
            {saved && (
              <Button variant="ghost" onClick={cancelEdit} disabled={saving}>
                Cancel
              </Button>
            )}
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <Button onClick={onTrace}>Trace my roof</Button>
            <Button variant="ghost" onClick={() => setEditing(true)}>
              Move the pin
            </Button>
          </div>
        )}
      </div>

      <div className="h-[60vh] lg:h-auto lg:min-h-[560px]">
        <MapView config={config} pin={pin} focusKey={focusKey} editable={editing} onPinChange={movePin} />
      </div>
    </div>
  );
}
