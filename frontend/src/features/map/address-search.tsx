"use client";

import { useState, type FormEvent } from "react";

import { MockBadge } from "@/components/mock-badge";
import { Button } from "@/components/ui/button";
import { ApiError, api, type Schemas } from "@/lib/api";
import { cn } from "@/lib/utils";

type Place = Schemas["PlaceOut"];
type State =
  | { kind: "idle" }
  | { kind: "searching" }
  | { kind: "error"; message: string }
  | { kind: "done"; response: Schemas["GeoSearchResponse"] };

/** Address search in Delhi via the Aroha API (Nominatim behind it). Searches on Enter only: 1 request a second. */
export function AddressSearch({ onPick }: { onPick: (place: Place) => void }) {
  const [query, setQuery] = useState("");
  const [state, setState] = useState<State>({ kind: "idle" });
  const tooShort = query.trim().length < 3;

  async function search(e: FormEvent) {
    e.preventDefault();
    if (tooShort || state.kind === "searching") return;
    setState({ kind: "searching" });
    try {
      const response = await api("get", "/api/geo/search", { query: { q: query.trim() } });
      setState({ kind: "done", response });
    } catch (err) {
      setState({ kind: "error", message: err instanceof ApiError ? err.message : "Search failed. Try again." });
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <form onSubmit={search} className="flex gap-2" role="search">
        <label htmlFor="address-q" className="sr-only">
          Search for your address
        </label>
        <input
          id="address-q"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="House, street or area"
          autoComplete="street-address"
          className="h-11 min-w-0 flex-1 rounded-md border border-border bg-card px-3 outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/20"
        />
        <Button type="submit" variant="secondary" disabled={tooShort || state.kind === "searching"}>
          {state.kind === "searching" ? "Searching…" : "Search"}
        </Button>
      </form>

      {state.kind === "error" && (
        <p role="alert" className="text-sm text-danger">
          {state.message}
        </p>
      )}
      {state.kind === "done" && (
        <div className="flex flex-col gap-1">
          {state.response.results.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Nothing found in the area Aroha covers (Delhi for now). Try a nearby landmark, or move the map and click
              on your roof.
            </p>
          ) : (
            <ul className="flex flex-col gap-1" aria-label="Search results">
              {state.response.results.map((place) => (
                <li key={`${place.lat},${place.lon}`}>
                  <button
                    type="button"
                    onClick={() => {
                      onPick(place);
                      setState({ kind: "idle" });
                      setQuery(place.display_name.split(",")[0]);
                    }}
                    className={cn(
                      "w-full rounded-md px-3 py-2 text-left text-sm hover:bg-muted",
                      "focus-visible:outline-2 focus-visible:outline-ring",
                    )}
                  >
                    {place.display_name}
                  </button>
                </li>
              ))}
            </ul>
          )}
          <p className="flex items-center gap-2 text-xs text-muted-foreground">
            Search by {state.response.attribution}
            {state.response.is_mock && <MockBadge what="address search" />}
          </p>
        </div>
      )}
    </div>
  );
}
