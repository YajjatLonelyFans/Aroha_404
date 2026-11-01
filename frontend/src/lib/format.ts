// Display formatting: Indian digit grouping, units, and dates in Asia/Kolkata.
// Missing values stay visibly missing ("—"); they are never shown as 0.

const TZ = "Asia/Kolkata";
const MISSING = "—";

type Num = number | null | undefined;

const isNum = (n: Num): n is number => typeof n === "number" && Number.isFinite(n);

export function formatNumber(n: Num, digits = 0): string {
  if (!isNum(n)) return MISSING;
  return n.toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

/** ₹1,23,456 (whole rupees). */
export function formatInr(n: Num): string {
  if (!isNum(n)) return MISSING;
  return n.toLocaleString("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });
}

/** "₹40,000–₹52,000", or a single value when both ends match. */
export function formatInrRange(lo: Num, hi: Num): string {
  return formatRange(lo, hi, formatInr);
}

export function formatKwh(n: Num): string {
  return isNum(n) ? `${formatNumber(n)} kWh` : MISSING;
}

/** System size: panels come in steps like 0.55 kW, so keep up to 2 decimals ("2.75", "3.3", "16.0"). */
export function formatKwpNumber(n: Num): string {
  if (!isNum(n)) return MISSING;
  return n.toLocaleString("en-IN", { minimumFractionDigits: 1, maximumFractionDigits: 2 });
}

export function formatKwp(n: Num): string {
  return isNum(n) ? `${formatKwpNumber(n)} kWp` : MISSING;
}

export function formatKwpRange(lo: Num, hi: Num): string {
  return isNum(lo) && isNum(hi) && lo !== hi ? `${formatKwpNumber(lo)}–${formatKwpNumber(hi)} kWp` : formatKwp(lo ?? hi);
}

export function formatArea(m2: Num): string {
  return isNum(m2) ? `${formatNumber(m2)} m²` : MISSING;
}

export function formatYearsRange(lo: Num, hi: Num): string {
  if (!isNum(lo) && !isNum(hi)) return MISSING;
  return `${formatRange(lo, hi, (n) => formatNumber(n, 1))} years`;
}

export function formatRange(lo: Num, hi: Num, fmt: (n: number) => string): string {
  if (isNum(lo) && isNum(hi)) return lo === hi ? fmt(lo) : `${fmt(lo)}–${fmt(hi)}`;
  if (isNum(lo)) return fmt(lo);
  if (isNum(hi)) return fmt(hi);
  return MISSING;
}

/** "1 Nov 2026". Accepts ISO strings from the backend (stored in UTC). */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return MISSING;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return MISSING;
  return d.toLocaleDateString("en-IN", { timeZone: TZ, day: "numeric", month: "short", year: "numeric" });
}

/** "1 Nov 2026, 3:05 pm". */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return MISSING;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return MISSING;
  return d.toLocaleString("en-IN", {
    timeZone: TZ,
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

/** "4,100–4,900 kWh". */
export function formatKwhRange(lo: Num, hi: Num): string {
  const r = formatRange(lo, hi, (n) => formatNumber(n));
  return r === MISSING ? r : `${r} kWh`;
}
