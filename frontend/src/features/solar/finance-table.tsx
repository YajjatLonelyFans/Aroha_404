import type { Schemas } from "@/lib/api";
import { formatInr, formatInrRange, formatKwhRange, formatKwpNumber, formatYearsRange } from "@/lib/format";
import { cn } from "@/lib/utils";

type Option = Schemas["EstimateOption"];

/** Cost, subsidy, savings and payback for each size (PRD FR-15, FR-16). Every figure is the backend's. */
export function FinanceTable({ options }: { options: Option[] }) {
  // One row per scheme that appears in any option, in first-seen order.
  const schemes = [...new Map(options.flatMap((o) => o.subsidy_breakdown.map((s) => [s.scheme_id, s.name]))).entries()];
  const hasIncentive = options.some((o) => o.annual_incentive_inr);
  const missing = [...new Set(options.flatMap((o) => o.missing))];

  return (
    <div className="flex flex-col gap-3">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[520px] text-sm tabular-nums">
          <caption className="sr-only">Cost, subsidy, savings and payback for each system size</caption>
          <thead>
            <tr className="border-b border-border">
              <th scope="col" className="py-2 text-left font-medium text-muted-foreground">
                System size
              </th>
              {options.map((o) => (
                <th
                  key={o.capacity_kwp}
                  scope="col"
                  className={cn("px-2 py-2 text-right align-bottom", o.recommended && "bg-primary/5")}
                >
                  {o.recommended && <span className="block text-xs font-medium text-primary">Recommended</span>}
                  <span className="font-semibold">{formatKwpNumber(o.capacity_kwp)} kWp</span>
                  <span className="block text-xs font-normal text-muted-foreground">{o.panel_count} panels</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <Row label="Yearly generation" options={options} value={(o) => formatKwhRange(o.annual_kwh.p10, o.annual_kwh.p90)} />
            <Row label="Cost before subsidy" options={options} value={(o) => formatInr(o.gross_cost_inr)} />
            {schemes.map(([id, name]) => (
              <Row
                key={id}
                label={name}
                sub
                options={options}
                value={(o) => {
                  const line = o.subsidy_breakdown.find((s) => s.scheme_id === id);
                  return line ? `− ${formatInr(line.amount_inr)}` : "—";
                }}
              />
            ))}
            <Row label="You pay (after subsidy)" strong options={options} value={(o) => formatInr(o.net_cost_inr)} />
            <Row
              label="Savings a year"
              options={options}
              value={(o) => formatInrRange(o.annual_savings_inr.low, o.annual_savings_inr.high)}
            />
            <Row
              label="Pays for itself in"
              strong
              options={options}
              value={(o) => formatYearsRange(o.payback_years.low, o.payback_years.high)}
            />
            {hasIncentive && (
              <>
                <Row
                  label="Delhi generation incentive"
                  options={options}
                  value={(o) =>
                    o.annual_incentive_inr
                      ? `${formatInrRange(o.annual_incentive_inr.low, o.annual_incentive_inr.high)} a year${o.incentive_years ? ` for ${o.incentive_years} years` : ""}`
                      : "—"
                  }
                />
                <Row
                  label="Pays for itself, with incentive"
                  options={options}
                  value={(o) =>
                    o.payback_years_with_incentive
                      ? formatYearsRange(o.payback_years_with_incentive.low, o.payback_years_with_incentive.high)
                      : "—"
                  }
                />
              </>
            )}
          </tbody>
        </table>
      </div>
      {missing.length > 0 && (
        <p className="text-sm text-warning">
          Some figures can&apos;t be worked out yet ({missing.join(", ")}), so they show as “—”.
        </p>
      )}
      <p className="text-sm text-muted-foreground">
        Ranges cover sunnier and cloudier years. Subsidies count only verified, current schemes, and approval is decided
        by the authorities.
      </p>
    </div>
  );
}

function Row({
  label,
  options,
  value,
  strong,
  sub,
}: {
  label: string;
  options: Option[];
  value: (o: Option) => string;
  strong?: boolean;
  sub?: boolean;
}) {
  return (
    <tr className={cn("border-b border-border last:border-0", strong && "font-semibold")}>
      <th scope="row" className={cn("py-2 text-left font-normal", sub && "pl-3 text-muted-foreground", strong && "font-semibold")}>
        {label}
      </th>
      {options.map((o) => (
        <td key={o.capacity_kwp} className={cn("px-2 py-2 text-right", o.recommended && "bg-primary/5", sub && "text-muted-foreground")}>
          {value(o)}
        </td>
      ))}
    </tr>
  );
}
