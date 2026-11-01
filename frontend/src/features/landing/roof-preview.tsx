// The landing page's one bright element: the real SSCBS main building, with the panels Aroha's own
// layout code packs onto its roof. Shapes and figures come from sscbs-roof.json, written by
// `python -m scripts.build_landing_preview` (footprint © OpenStreetMap contributors).
import roof from "./sscbs-roof.json";

import { formatArea, formatKwp, formatNumber } from "@/lib/format";

// Same marks as the roof map: amber traced outline, amber panels with a forest edge.
const AMBER = "var(--aroha-amber)";
const FOREST = "var(--aroha-forest)";
const PAD = 4; // metres of air around the building inside the drawing

const path = (ring: number[][]) => `M${ring.map(([x, y]) => `${x},${y}`).join("L")}Z`;

function Roof() {
  const { width_m: w, height_m: h } = roof;
  const outline = path(roof.outline) + roof.courtyard.map(path).join("");
  return (
    <svg
      viewBox={`${-PAD} ${-PAD} ${w + PAD * 2} ${h + PAD * 2}`}
      role="img"
      aria-label={`Top-down drawing of the SSCBS main building roof around its courtyard, with ${roof.figures.panel_count} solar panels laid out on it`}
      className="h-auto w-full"
    >
      {/* the roof, traced; the courtyard is a hole (even-odd fill) */}
      <path d={outline} fill="#ebe8df" fillRule="evenodd" />
      <path d={outline} fill={AMBER} fillOpacity="0.08" fillRule="evenodd" stroke={AMBER} strokeWidth="0.6" strokeLinejoin="round" />
      {/* every panel the packing code fits, in rows facing south */}
      {roof.panels.map((p, i) => (
        <path key={i} d={path(p)} fill={AMBER} stroke={FOREST} strokeWidth="0.12" />
      ))}
      {/* traced corners */}
      {roof.outline.slice(0, -1).map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r="0.7" fill="#fff" stroke={FOREST} strokeWidth="0.3" />
      ))}
    </svg>
  );
}

export function RoofPreview() {
  const f = roof.figures;
  return (
    <figure className="rounded-xl border border-border bg-card p-5 shadow-[0_8px_24px_rgba(0,0,0,0.06)]">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between sm:gap-4">
        <p className="font-heading text-base font-semibold text-primary">The SSCBS roof, laid out by Aroha</p>
        <p className="text-sm text-muted-foreground">Rohini, Delhi</p>
      </div>
      <div className="mx-auto mt-4 max-w-md">
        <Roof />
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-3 border-t border-border pt-4 tabular-nums">
        <Figure label="Roof traced" value={formatArea(f.outline_area_m2)} />
        <Figure label="Usable for panels" value={formatArea(f.usable_area_m2)} />
        <Figure label="Panels that fit" value={`${formatNumber(f.panel_count)} × ${formatNumber(f.module_wp)} W`} />
        <Figure label="Capacity" value={formatKwp(f.capacity_kwp)} />
      </dl>
      <figcaption className="mt-4 text-xs text-muted-foreground">
        Footprint © OpenStreetMap contributors. Edge walkway, row spacing and panel layout by the same code that works
        out a home&apos;s roof. A campus is not a home, so no savings are shown here.
      </figcaption>
    </figure>
  );
}

function Figure({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="mt-1 whitespace-nowrap text-base font-medium text-foreground sm:text-lg">{value}</dd>
    </div>
  );
}
