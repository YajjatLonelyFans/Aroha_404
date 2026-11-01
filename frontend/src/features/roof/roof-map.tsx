"use client";

import "maplibre-gl/dist/maplibre-gl.css";

import type { FeatureCollection } from "geojson";
import type { GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";
import { useEffect, useImperativeHandle, useRef, useState, type Ref } from "react";
import type { GeoJSONStoreFeatures, TerraDraw } from "terra-draw";

import { MockBadge } from "@/components/mock-badge";
import { AMBER, FOREST, NO_GO_GREY, ROOF_ZOOM, createMap } from "@/features/map/maplibre";
import type { LatLon } from "@/features/map/map-view";
import type { Schemas } from "@/lib/api";

import type { Drawing, NoGoKind, Polygon } from "./roof-shapes";

/** What the map lets the person do right now. */
export type Tool = "draw-outline" | "draw-nogo" | "edit" | "view";

export type RoofMapHandle = {
  clearOutline: () => void;
  removeNoGo: (id: string) => void;
};

type Props = {
  config: Schemas["MapConfig"];
  center: LatLon;
  /** Shapes to show when the map opens (a saved drawing); later changes come from drawing. */
  initial: { outline: Polygon | null; noGo: { kind: NoGoKind; geometry: Polygon }[] };
  tool: Tool;
  noGoKind: NoGoKind;
  /** Panel rectangles from the backend, shown on top of the roof. */
  panels: FeatureCollection | null;
  onChange: (drawing: Drawing) => void;
  /** Called when a shape has been finished, so the page can leave drawing mode. */
  onFinish: (what: "outline" | "nogo") => void;
  ref?: Ref<RoofMapHandle>;
};

const OUTLINE = "outline";
const NOGO = "nogo";
// terra-draw closes a shape when a click lands this close to its first corner (default 40 px),
// which cut small tanks and heaters short after three corners.
const CLOSE_DISTANCE_PX = 12;

function snapshot(draw: TerraDraw): Drawing {
  const done = draw
    .getSnapshot()
    .filter((f) => f.geometry.type === "Polygon" && !f.properties.currentlyDrawing);
  const outline = done.find((f) => f.properties.mode === OUTLINE);
  return {
    outline: outline ? (outline.geometry as Polygon) : null,
    noGo: done
      .filter((f) => f.properties.mode === NOGO)
      .map((f) => ({ id: String(f.id), kind: (f.properties.kind as NoGoKind) ?? "other", geometry: f.geometry as Polygon })),
  };
}

/**
 * Satellite map for tracing the roof (amber) and no-go areas (grey), with corners that can be
 * dragged, and the backend's panel layout drawn on top. Uses terra-draw for the drawing.
 */
export function RoofMap({ config, center, initial, tool, noGoKind, panels, onChange, onFinish, ref }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const drawRef = useRef<TerraDraw | null>(null);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);

  const latest = useRef({ noGoKind, onChange, onFinish, initial });
  useEffect(() => {
    latest.current = { noGoKind, onChange, onFinish, initial };
  });

  useImperativeHandle(ref, () => ({
    clearOutline() {
      const draw = drawRef.current;
      if (!draw) return;
      const ids = draw.getSnapshot().filter((f) => f.properties.mode === OUTLINE).map((f) => f.id!);
      if (ids.length) draw.removeFeatures(ids);
      latest.current.onChange(snapshot(draw));
    },
    removeNoGo(id) {
      const draw = drawRef.current;
      if (!draw) return;
      if (draw.getSnapshotFeature(id)) draw.removeFeatures([id]);
      latest.current.onChange(snapshot(draw));
    },
  }));

  // Create the map and the drawing layer once.
  useEffect(() => {
    let cancelled = false;
    let map: MapLibreMap | null = null;
    let draw: TerraDraw | null = null;
    // Safe to call twice: from the effect cleanup, and from a load that finishes after it.
    const dispose = () => {
      try {
        draw?.stop();
      } catch {
        // the map may already be gone
      }
      draw = null;
      map?.remove();
      map = null;
    };
    (async () => {
      map = await createMap(containerRef.current!, config, { center: [center.lon, center.lat], zoom: ROOF_ZOOM });
      if (cancelled) return dispose();
      const [td, { TerraDrawMapLibreGLAdapter }] = await Promise.all([
        import("terra-draw"),
        import("terra-draw-maplibre-gl-adapter"),
      ]);
      if (cancelled) return dispose();
      const notSelfIntersecting = (feature: GeoJSONStoreFeatures, { updateType }: { updateType: string }) =>
        updateType === "finish" || updateType === "commit" ? td.ValidateNotSelfIntersecting(feature) : { valid: true };
      const corners = { draggable: true, midpoints: true, deletable: true };
      draw = new td.TerraDraw({
        adapter: new TerraDrawMapLibreGLAdapter({ map }),
        modes: [
          new td.TerraDrawPolygonMode({
            modeName: OUTLINE,
            pointerDistance: CLOSE_DISTANCE_PX,
            validation: notSelfIntersecting,
            styles: { fillColor: AMBER, fillOpacity: 0.12, outlineColor: AMBER, outlineWidth: 3,
              closingPointColor: AMBER, closingPointOutlineColor: FOREST },
          }),
          new td.TerraDrawPolygonMode({
            modeName: NOGO,
            pointerDistance: CLOSE_DISTANCE_PX,
            validation: notSelfIntersecting,
            styles: { fillColor: NO_GO_GREY, fillOpacity: 0.55, outlineColor: "#1f2937", outlineWidth: 2,
              closingPointColor: NO_GO_GREY, closingPointOutlineColor: "#1f2937" },
          }),
          new td.TerraDrawSelectMode({
            flags: {
              [OUTLINE]: { feature: { draggable: false, coordinates: corners } },
              [NOGO]: { feature: { draggable: true, coordinates: corners } },
            },
            styles: { selectedPolygonColor: AMBER, selectedPolygonOutlineColor: FOREST, selectedPointColor: FOREST,
              selectedPointOutlineColor: "#ffffff", midPointColor: AMBER, midPointOutlineColor: FOREST },
          }),
        ],
      });
      draw.start();

      const { initial: start } = latest.current;
      const features: GeoJSONStoreFeatures[] = [];
      if (start.outline) {
        features.push({ type: "Feature", id: draw.getFeatureId(), geometry: start.outline, properties: { mode: OUTLINE } });
      }
      for (const n of start.noGo) {
        features.push({ type: "Feature", id: draw.getFeatureId(), geometry: n.geometry, properties: { mode: NOGO, kind: n.kind } });
      }
      if (features.length) draw.addFeatures(features);

      const current = draw;
      current.on("finish", (id) => {
        const feature = current.getSnapshotFeature(id);
        if (!feature) return;
        if (feature.properties.mode === OUTLINE) {
          // One roof outline at a time: a new one replaces the old.
          const older = current.getSnapshot().filter((f) => f.properties.mode === OUTLINE && f.id !== id).map((f) => f.id!);
          if (older.length) current.removeFeatures(older);
          latest.current.onFinish("outline");
        } else if (feature.properties.mode === NOGO) {
          current.updateFeatureProperties(id, { kind: latest.current.noGoKind });
          latest.current.onFinish("nogo");
        }
        latest.current.onChange(snapshot(current));
      });
      // Corner drags and deletions in select mode.
      current.on("change", (_ids, type) => {
        if (type === "update" || type === "delete") latest.current.onChange(snapshot(current));
      });

      map.addSource("panels", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({ id: "panels-fill", type: "fill", source: "panels", paint: { "fill-color": AMBER, "fill-opacity": 0.9 } });
      map.addLayer({ id: "panels-line", type: "line", source: "panels", paint: { "line-color": FOREST, "line-width": 1 } });

      mapRef.current = map;
      drawRef.current = draw;
      latest.current.onChange(snapshot(draw));
      setReady(true);
    })().catch(() => {
      if (!cancelled) setFailed(true);
    });
    return () => {
      cancelled = true;
      setReady(false);
      drawRef.current = null;
      mapRef.current = null;
      dispose();
    };
    // The map is built once per page; the pin and config do not change while it is open.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Switch drawing mode with the page's tool.
  useEffect(() => {
    const draw = drawRef.current;
    if (!ready || !draw) return;
    const mode = { "draw-outline": OUTLINE, "draw-nogo": NOGO, edit: "select", view: "static" }[tool];
    if (draw.getMode() !== mode) draw.setMode(mode);
  }, [ready, tool]);

  // Show the panel layout.
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    (map.getSource("panels") as GeoJSONSource | undefined)?.setData(panels ?? { type: "FeatureCollection", features: [] });
  }, [ready, panels]);

  return (
    <div className="relative h-full min-h-80 w-full overflow-hidden rounded-lg border border-border bg-muted">
      {/* maplibre makes this element position: relative, so size it rather than using inset. */}
      <div ref={containerRef} className="h-full w-full" aria-label="Satellite map of your roof" role="region" />
      {config.is_mock && (
        <div className="absolute left-3 top-3">
          <MockBadge what="satellite imagery" />
        </div>
      )}
      {(!config.satellite_available || failed) && (
        <p className="absolute inset-x-3 top-3 rounded-md bg-card/95 px-3 py-2 text-sm shadow-sm">
          {failed ? "The map could not load in this browser." : config.detail}
        </p>
      )}
    </div>
  );
}
