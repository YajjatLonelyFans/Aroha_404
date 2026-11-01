"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

import type { LatLon } from "./map-view";

type State =
  | { kind: "idle" }
  | { kind: "locating" }
  | { kind: "error"; message: string }
  | { kind: "found"; accuracyM: number };

// Beyond this the fix is from Wi-Fi or cell towers, not GPS, and may be a street or more away.
const ROUGH_FIX_M = 100;

const FAILURES: Record<number, string> = {
  1: "Location is blocked for this site. Allow it in your browser's site settings, or search for your address.",
  2: "Your device could not find its location. Search for your address instead.",
  3: "Finding your location took too long. Try again outdoors, or search for your address.",
};

/**
 * Drops the pin at the device's own position (browser geolocation). The position stays in the
 * browser until the homeowner saves the pin, exactly like a pin placed by hand.
 */
export function CurrentLocation({ onLocate }: { onLocate: (pin: LatLon) => void }) {
  const [state, setState] = useState<State>({ kind: "idle" });

  function locate() {
    // Browsers only offer geolocation on HTTPS or localhost.
    if (!window.isSecureContext || !("geolocation" in navigator)) {
      setState({ kind: "error", message: "This browser can't share your location here. Search for your address." });
      return;
    }
    setState({ kind: "locating" });
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        onLocate({ lat: coords.latitude, lon: coords.longitude });
        setState({ kind: "found", accuracyM: coords.accuracy });
      },
      (err) => setState({ kind: "error", message: FAILURES[err.code] ?? FAILURES[2] }),
      { enableHighAccuracy: true, timeout: 15_000, maximumAge: 0 },
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <Button variant="secondary" onClick={locate} disabled={state.kind === "locating"}>
        {state.kind === "locating" ? "Finding your location…" : "Use my current location"}
      </Button>
      {state.kind === "found" && (
        <p
          role="status"
          className={cn("text-sm", state.accuracyM > ROUGH_FIX_M ? "text-warning" : "text-muted-foreground")}
        >
          {state.accuracyM > ROUGH_FIX_M
            ? `This fix is rough, within about ${formatNumber(state.accuracyM)} m. Search for your address or drag the pin onto your roof.`
            : `Found you, within about ${formatNumber(state.accuracyM)} m. Drag the pin onto your roof if it is off.`}
        </p>
      )}
      {state.kind === "error" && (
        <p role="alert" className="text-sm text-danger">
          {state.message}
        </p>
      )}
    </div>
  );
}
