// Roof drawing types and labels. Areas here are a live preview only; the backend computes the real ones.
import turfArea from "@turf/area";
import type { Polygon } from "geojson";

import type { Schemas } from "@/lib/api";

export type { Polygon };
export type NoGoKind = Schemas["NoGoArea"]["kind"];
export type ShadeLevel = Schemas["Shading"]["east"];
export type Side = keyof Schemas["Shading"];

export type NoGo = { id: string; kind: NoGoKind; geometry: Polygon };
export type Drawing = { outline: Polygon | null; noGo: NoGo[] };

export const NO_GO_KINDS: { value: NoGoKind; label: string }[] = [
  { value: "water_tank", label: "Water tank" },
  { value: "stair_room", label: "Stair room" },
  { value: "solar_heater", label: "Solar water heater" },
  { value: "other", label: "Something else" },
];

export const SIDES: { value: Side; label: string }[] = [
  { value: "east", label: "East (morning sun)" },
  { value: "south", label: "South (midday sun)" },
  { value: "west", label: "West (evening sun)" },
  { value: "north", label: "North" },
];

export const SHADE_LEVELS: { value: ShadeLevel; label: string }[] = [
  { value: "none", label: "None" },
  { value: "partial", label: "Some" },
  { value: "heavy", label: "A lot" },
];

// Which way a sloped roof faces. Azimuth convention matches the backend: 0 = south, -90 = east, 90 = west.
export const FACINGS: { label: string; azimuth: number }[] = [
  { label: "South", azimuth: 0 },
  { label: "South-east", azimuth: -45 },
  { label: "South-west", azimuth: 45 },
  { label: "East", azimuth: -90 },
  { label: "West", azimuth: 90 },
  { label: "North-east", azimuth: -135 },
  { label: "North-west", azimuth: 135 },
  { label: "North", azimuth: 180 },
];

export const kindLabel = (kind: NoGoKind) => NO_GO_KINDS.find((k) => k.value === kind)?.label ?? kind;

/** Geodesic area in m², for the live readout while drawing. */
export function areaM2(polygon: Polygon): number {
  return turfArea(polygon);
}
