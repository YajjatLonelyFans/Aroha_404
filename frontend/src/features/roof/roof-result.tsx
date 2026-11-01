import type { Schemas } from "@/lib/api";
import { formatArea, formatKwp, formatKwpRange, formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

type Assessment = Schemas["RoofAssessResponse"];

const CONFIDENCE: Record<Assessment["confidence"], { label: string; className: string }> = {
  high: { label: "High confidence", className: "border-success text-success" },
  medium: { label: "Medium confidence", className: "border-warning text-warning" },
  low: { label: "Low confidence", className: "border-danger text-danger" },
};

/** Panels and capacity for the roof, with every area deduction shown (PRD FR-4, FR-6, FR-7). All numbers come from the backend. */
export function RoofResult({ result }: { result: Assessment }) {
  const confidence = CONFIDENCE[result.confidence];
  const { min, likely, max } = result.capacity_kwp;
  return (
    <div className="flex flex-col gap-5">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-2xl tabular-nums">Up to {formatNumber(result.panel_count)} panels fit</h2>
          <span className={cn("rounded-full border px-2 py-0.5 text-xs font-medium", confidence.className)}>
            {confidence.label}
          </span>
        </div>
        <p className="mt-1 tabular-nums">
          {min === max
            ? `${formatKwp(likely)} at most on this roof`
            : `${formatKwpRange(min, max)} at most on this roof, most likely ${formatKwp(likely)}`}
        </p>
        <p className="mt-1 text-sm text-muted-foreground">
          This is what the roof can hold, not a recommendation. The estimate sizes the system to your electricity use,
          which is often smaller. {formatNumber(result.module_wp)} W panels{result.traced ? ", drawn on the map" : ""}.
        </p>
      </div>

      <table className="w-full text-sm tabular-nums">
        <caption className="sr-only">How the usable roof area is worked out</caption>
        <tbody>
          <Row label="Roof outline" value={formatArea(result.outline_area_m2)} />
          <Row label="Walkway along the edge" value={`− ${formatArea(result.setback_area_m2)}`} />
          <Row label="No-go areas and clearance" value={`− ${formatArea(result.no_go_area_m2)}`} />
          <Row label="Usable for panels" value={formatArea(result.usable_area_m2)} strong />
        </tbody>
      </table>

      {result.constraints.length > 0 && (
        <div>
          <h3 className="text-sm">What limits this roof</h3>
          <ul className="mt-2 flex list-disc flex-col gap-1 pl-5 text-sm">
            {result.constraints.map((c) => (
              <li key={c.code}>{c.message}</li>
            ))}
          </ul>
        </div>
      )}

      <details className="text-sm">
        <summary className="cursor-pointer font-medium text-primary">Assumptions used</summary>
        <ul className="mt-2 flex list-disc flex-col gap-1 pl-5 text-muted-foreground">
          {result.assumptions.map((a) => (
            <li key={a}>{a}</li>
          ))}
        </ul>
      </details>
    </div>
  );
}

function Row({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <tr className={cn("border-b border-border last:border-0", strong && "font-semibold")}>
      <th scope="row" className="py-2 text-left font-normal">
        {label}
      </th>
      <td className="py-2 text-right">{value}</td>
    </tr>
  );
}
