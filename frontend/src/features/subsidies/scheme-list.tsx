import type { Schemas } from "@/lib/api";
import { formatDate, formatInr, formatKwpNumber, formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

type Scheme = Schemas["SchemeResult"];

// Status colours always come with a symbol and a word, never colour alone.
const CHIP: Record<Scheme["eligible"], { label: string; symbol: string; className: string }> = {
  yes: { label: "Eligible", symbol: "✓", className: "border-success text-success" },
  no: { label: "Not eligible", symbol: "✕", className: "border-danger text-danger" },
  unknown: { label: "Needs checking", symbol: "?", className: "border-warning text-warning" },
};

const JURISDICTION: Record<string, string> = { central: "Central government", delhi: "Delhi government" };

function amountText(s: Scheme): string | null {
  if (s.amount_inr != null) return `${formatInr(s.amount_inr)} towards the cost`;
  if (s.inr_per_kwh != null) {
    return `₹${formatNumber(s.inr_per_kwh, s.inr_per_kwh % 1 ? 2 : 0)} for each unit generated${s.incentive_years ? `, for ${s.incentive_years} years` : ""}`;
  }
  return null;
}

/** Eligibility for each scheme with reasons, conditions and its dated source (PRD FR-17, FR-18). */
export function SchemeList({ eligibility }: { eligibility: Schemas["EligibilityResponse"] }) {
  return (
    <div className="flex flex-col gap-4">
      <p className="tabular-nums">
        Subsidy counted in your estimate
        {eligibility.capacity_kwp != null ? ` for a ${formatKwpNumber(eligibility.capacity_kwp)} kWp system` : ""}:{" "}
        <span className="font-semibold">{formatInr(eligibility.total_subsidy_inr)}</span>
      </p>
      <ul className="grid gap-4 md:grid-cols-2" aria-label="Schemes">
        {eligibility.schemes.map((s) => (
          <SchemeCard key={s.scheme_id} scheme={s} />
        ))}
      </ul>
      {eligibility.notes.length > 0 && (
        <ul className="flex list-disc flex-col gap-1 pl-5 text-sm text-muted-foreground">
          {eligibility.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}
      <p className="text-sm text-muted-foreground">{eligibility.disclaimer}</p>
    </div>
  );
}

function SchemeCard({ scheme: s }: { scheme: Scheme }) {
  const chip = CHIP[s.eligible];
  const amount = amountText(s);
  const unverified = s.status !== "verified";
  return (
    <li className="flex flex-col gap-3 rounded-lg border border-border bg-card p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs text-muted-foreground">{JURISDICTION[s.jurisdiction] ?? s.jurisdiction}</p>
          <h3 className="text-base">{s.name}</h3>
        </div>
        <span className={cn("shrink-0 whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium", chip.className)}>
          <span aria-hidden="true">{chip.symbol} </span>
          {chip.label}
        </span>
      </div>

      {amount && (
        <p className={cn("tabular-nums", s.counts_in_estimate ? "font-medium" : "text-muted-foreground")}>{amount}</p>
      )}
      {!s.counts_in_estimate && (
        <p className="rounded-md bg-muted px-3 py-2 text-sm">
          {unverified
            ? "Needs verification: not counted in your estimate until it is checked against the official source"
            : "Not counted in your estimate."}
        </p>
      )}

      {s.reasons.length > 0 && (
        <ul className="flex list-disc flex-col gap-1 pl-5 text-sm">
          {s.reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      )}
      {s.conditions.length > 0 && (
        <div className="text-sm">
          <p className="font-medium">You&apos;ll need to confirm</p>
          <ul className="mt-1 flex list-disc flex-col gap-1 pl-5 text-muted-foreground">
            {s.conditions.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </div>
      )}

      <p className="mt-auto text-xs text-muted-foreground">
        <a href={s.source_url} target="_blank" rel="noreferrer" className="font-medium text-primary underline">
          Official source
        </a>{" "}
        · Verified on {formatDate(s.verified_on)}
        {s.review_by ? ` · Review by ${formatDate(s.review_by)}` : ""}
      </p>
    </li>
  );
}
