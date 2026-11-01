// maplibre-gl starts its worker from a URL next to its own module, which the bundler moves.
// Copy the worker (same version as the installed package) into public/ so it can be served
// from a fixed path; map-view.tsx points maplibre at it with setWorkerUrl().
import { copyFileSync, mkdirSync } from "node:fs";

mkdirSync("public/maplibre", { recursive: true });
copyFileSync("node_modules/maplibre-gl/dist/maplibre-gl-worker.mjs", "public/maplibre/maplibre-gl-worker.mjs");
