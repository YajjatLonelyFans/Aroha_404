"use client";

import "maplibre-gl/dist/maplibre-gl.css";

import type { Map as MapLibreMap, Marker } from "maplibre-gl";
import { useEffect, useRef, useState } from "react";

import { MockBadge } from "@/components/mock-badge";
import type { Schemas } from "@/lib/api";

import { AMBER, CITY_ZOOM, DELHI_CENTER, HOUSE_ZOOM, TILE_FAILURES_BEFORE_NOTICE, createMap } from "./maplibre";

export type LatLon = { lat: number; lon: number };

type Props = {
  config: Schemas["MapConfig"];
  pin: LatLon | null;
  /** Bump to move the camera to the pin (after a search pick or on load). */
  focusKey: number;
  editable: boolean;
  onPinChange: (pin: LatLon) => void;
};

/** Satellite map with one draggable pin. Imagery comes through the Aroha API (the key stays on the server). */
export function MapView({ config, pin, focusKey, editable, onPinChange }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const markerRef = useRef<Marker | null>(null);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const [tileFailures, setTileFailures] = useState(0);

  // Latest values for the map's event handlers, which are bound once.
  const latest = useRef({ editable, onPinChange });
  useEffect(() => {
    latest.current = { editable, onPinChange };
  });

  // Create the map (in the browser only).
  useEffect(() => {
    let cancelled = false;
    let map: MapLibreMap | null = null;
    createMap(containerRef.current!, config, { center: DELHI_CENTER, zoom: CITY_ZOOM }, () =>
      setTileFailures((n) => n + 1),
    )
      .then((created) => {
        map = created;
        if (cancelled) return created.remove();
        created.on("click", (e) => {
          if (latest.current.editable) latest.current.onPinChange({ lat: e.lngLat.lat, lon: e.lngLat.lng });
        });
        mapRef.current = created;
        setReady(true);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
      markerRef.current = null;
      mapRef.current = null;
      setReady(false);
      map?.remove();
    };
  }, [config]);

  // Keep the marker in step with the pin.
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    if (!pin) {
      markerRef.current?.remove();
      markerRef.current = null;
      return;
    }
    let cancelled = false;
    import("maplibre-gl").then(({ Marker }) => {
      if (cancelled) return;
      if (!markerRef.current) {
        const marker = new Marker({ color: AMBER, draggable: editable });
        marker.on("dragend", () => {
          const { lat, lng } = marker.getLngLat();
          latest.current.onPinChange({ lat, lon: lng });
        });
        markerRef.current = marker.setLngLat([pin.lon, pin.lat]).addTo(map);
      } else {
        markerRef.current.setLngLat([pin.lon, pin.lat]).setDraggable(editable);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [ready, pin, editable]);

  // Move the camera to the pin when asked.
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !pin || focusKey === 0) return;
    map.flyTo({ center: [pin.lon, pin.lat], zoom: Math.min(HOUSE_ZOOM, config.max_zoom), speed: 1.6 });
    // Only on a new focus request, not on every drag.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, focusKey]);

  return (
    <div className="relative h-full min-h-80 w-full overflow-hidden rounded-lg border border-border bg-muted">
      {/* maplibre makes this element position: relative, so size it rather than using inset. */}
      <div ref={containerRef} className="h-full w-full" aria-label="Satellite map" role="region" />
      {config.is_mock && (
        <div className="absolute left-3 top-3">
          <MockBadge what="satellite imagery" />
        </div>
      )}
      {config.satellite_available && !failed && tileFailures >= TILE_FAILURES_BEFORE_NOTICE && (
        <p role="status" className="absolute inset-x-3 bottom-10 rounded-md bg-card/95 px-3 py-2 text-sm shadow-sm">
          Satellite imagery isn&apos;t loading right now. Search your address or click where your house is: the pin still
          works without the picture.
        </p>
      )}
      {(!config.satellite_available || failed) && (
        <p className="absolute inset-x-3 top-3 rounded-md bg-card/95 px-3 py-2 text-sm shadow-sm">
          {failed ? "The map could not load in this browser." : config.detail}
        </p>
      )}
    </div>
  );
}
