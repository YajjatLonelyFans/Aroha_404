// Shared MapLibre setup: satellite style through the Aroha API, the worker URL and controls.
// maplibre-gl touches `window`, so it is imported lazily, in the browser only.
import type { Map as MapLibreMap, StyleSpecification } from "maplibre-gl";

import { apiUrl, type Schemas } from "@/lib/api";

export const DELHI_CENTER: [number, number] = [77.209, 28.6139]; // [lon, lat], India Gate area
export const CITY_ZOOM = 11;
// MapLibre zooms count 512 px tiles, one level "closer" than the 256 px imagery tiles: zoom 18 here
// shows z19 imagery at about 0.26 m per pixel in Delhi. Closer than that, the imagery is just upscaled.
export const HOUSE_ZOOM = 17.5;
export const ROOF_ZOOM = 18;

// Brand colours used on the map (docs/DESIGN_SYSTEM.md).
export const AMBER = "#e6a43a";
export const FOREST = "#073f32";
export const NO_GO_GREY = "#6b7280";

const WORKER_URL = "/maplibre/maplibre-gl-worker.mjs"; // copied by scripts/copy-maplibre-worker.mjs

function buildStyle(config: Schemas["MapConfig"]): StyleSpecification {
  const background = { id: "background", type: "background" as const, paint: { "background-color": "#e9e6dc" } };
  if (!config.satellite_available) return { version: 8, sources: {}, layers: [background] };
  return {
    version: 8,
    sources: {
      satellite: {
        type: "raster",
        tiles: [apiUrl(config.tile_url)],
        tileSize: 256,
        maxzoom: config.max_zoom,
        attribution: config.attribution,
      },
    },
    layers: [background, { id: "satellite", type: "raster", source: "satellite" }],
  };
}

/** A map with satellite imagery, zoom buttons and the imagery credit, resolved once its style has loaded. */
export async function createMap(
  container: HTMLElement,
  config: Schemas["MapConfig"],
  view: { center: [number, number]; zoom: number },
): Promise<MapLibreMap> {
  const { Map, NavigationControl, AttributionControl, ScaleControl, getVersion, setWorkerUrl } = await import("maplibre-gl");
  setWorkerUrl(`${WORKER_URL}?v=${getVersion()}`);
  const map = new Map({
    container,
    style: buildStyle(config),
    center: view.center,
    zoom: view.zoom,
    maxZoom: config.max_zoom + 2, // a little over-zoom helps place pins and corners precisely
    attributionControl: false,
  });
  map.addControl(new NavigationControl({ showCompass: false }), "top-right");
  map.addControl(new AttributionControl({ compact: false }), "bottom-right");
  // A metric scale bar, so a traced roof can be checked against a known size (a car is about 4.5 m).
  map.addControl(new ScaleControl({ unit: "metric", maxWidth: 120 }), "bottom-left");
  // A slow imagery provider can fail a few tiles (the backend answers 503). The map just shows
  // those squares blank until it is moved, so log them quietly; anything else is a real error.
  map.on("error", ({ error }) => {
    if (String(error?.message ?? "").includes("/api/tiles/satellite/")) console.warn("Satellite tile not loaded:", error.message);
    else console.error(error);
  });
  if (!map.loaded()) await map.once("load");
  return map;
}
