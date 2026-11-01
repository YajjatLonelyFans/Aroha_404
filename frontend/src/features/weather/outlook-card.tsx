import { MockBadge } from "@/components/mock-badge";
import type { Schemas } from "@/lib/api";
import { formatDateTime, formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

type Forecast = Schemas["ForecastResponse"];
type Outlook = NonNullable<Forecast["daily"][number]["outlook"]>;

const OUTLOOK: Record<Outlook, { label: string; className: string }> = {
  sunny: { label: "Sunny", className: "bg-accent/25" },
  mixed: { label: "Mixed", className: "bg-accent/10" },
  cloudy: { label: "Cloudy", className: "bg-muted" },
  rain: { label: "Rain", className: "bg-muted" },
};

function dayName(date: string): string {
  // Dates are local (Asia/Kolkata) calendar days.
  return new Date(`${date}T12:00:00+05:30`).toLocaleDateString("en-IN", { weekday: "short", day: "numeric", timeZone: "Asia/Kolkata" });
}

/** The next 7 days, kept visually apart from the long-term estimate it never feeds (CLAUDE.md rule 4, PRD FR-12). */
export function OutlookCard({ forecast, error }: { forecast: Forecast | null; error: string | null }) {
  return (
    <section aria-labelledby="outlook-title" className="rounded-lg border border-dashed border-border bg-card p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id="outlook-title" className="text-lg">
          {forecast?.label ?? "Short-term outlook"}
        </h3>
        {forecast?.is_mock && <MockBadge what="weather" />}
      </div>
      <p className="mt-1 text-sm text-muted-foreground">
        Sunlight on your panels over the next week. This is a forecast; it does not change the yearly estimate above.
      </p>
      {error ? (
        <p className="mt-3 text-sm text-muted-foreground">The outlook isn&apos;t available right now ({error}).</p>
      ) : !forecast ? (
        <p className="mt-3 text-sm text-muted-foreground">Loading the outlook…</p>
      ) : (
        <>
          <ul className="mt-4 grid grid-cols-4 gap-2 sm:grid-cols-7" aria-label="Daily outlook">
            {forecast.daily.map((d) => {
              const look = d.outlook ? OUTLOOK[d.outlook] : null;
              return (
                <li key={d.date} className={cn("flex flex-col items-center gap-0.5 rounded-md p-2 text-center", look?.className ?? "bg-muted")}>
                  <span className="text-xs text-muted-foreground">{dayName(d.date)}</span>
                  <span className="text-sm font-medium">{look?.label ?? "—"}</span>
                  <span className="text-xs tabular-nums">
                    {d.gti_kwh_m2 == null ? "—" : `${formatNumber(d.gti_kwh_m2, 1)} kWh/m²`}
                  </span>
                  <span className="text-xs tabular-nums text-muted-foreground">
                    {d.temp_max_c == null ? "" : `${formatNumber(d.temp_max_c)}°C`}
                  </span>
                </li>
              );
            })}
          </ul>
          <p className="mt-3 text-xs text-muted-foreground">
            {forecast.sources.map((s) => s.name).join(", ")}, retrieved {formatDateTime(forecast.retrieved_at)}.
          </p>
        </>
      )}
    </section>
  );
}
