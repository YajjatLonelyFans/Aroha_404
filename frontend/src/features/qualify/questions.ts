// The four qualifying questions (PRD FR-1) and how answers map to the backend request.
import type { Schemas } from "@/lib/api";
import { checkMonthlyUnits } from "@/lib/validation";

type PropertyType = Schemas["CreateUserRequest"]["property_type"];
type Discom = Schemas["CreateUserRequest"]["discom"];
type YesNo = "yes" | "no";

export type Option<V extends string> = { value: V; label: string; hint?: string };

export type Answers = {
  property_type?: PropertyType;
  has_roof_rights?: YesNo;
  monthly_units_kwh: string; // kept as typed; parsed on submit
  discom?: Discom;
};

export const EMPTY_ANSWERS: Answers = { monthly_units_kwh: "" };

export const PROPERTY_OPTIONS: Option<PropertyType>[] = [
  { value: "independent_house", label: "Independent house", hint: "The whole building is yours" },
  { value: "builder_floor", label: "Builder floor", hint: "One floor in a building that shares the roof" },
  { value: "other", label: "Something else", hint: "A flat in a housing society, a shop or an office" },
];

export const ROOF_OPTIONS: Option<YesNo>[] = [
  { value: "yes", label: "Yes", hint: "I own the roof, or have written permission to use it" },
  { value: "no", label: "No, or not sure", hint: "The roof is shared or belongs to someone else" },
];

export const DISCOM_OPTIONS: Option<Discom>[] = [
  { value: "BRPL", label: "BSES Rajdhani (BRPL)", hint: "Mostly South and West Delhi" },
  { value: "BYPL", label: "BSES Yamuna (BYPL)", hint: "Mostly East and Central Delhi" },
  { value: "TPDDL", label: "Tata Power-DDL (TPDDL)", hint: "Mostly North and North-West Delhi" },
  { value: "NDMC", label: "NDMC", hint: "New Delhi Municipal Council area" },
  { value: "other", label: "Other or not sure", hint: "The supplier's name is at the top of your bill" },
];

export type Step = {
  key: keyof Answers;
  title: string;
  help: string;
};

export const STEPS: Step[] = [
  { key: "property_type", title: "What kind of home is it?", help: "Aroha covers independent houses and builder floors in Delhi." },
  { key: "has_roof_rights", title: "Can you use the roof for solar panels?", help: "Panels need the roof owner's agreement." },
  { key: "monthly_units_kwh", title: "About how many units do you use a month?", help: "Units (kWh) are on your electricity bill. A rough figure is fine." },
  { key: "discom", title: "Who supplies your electricity?", help: "This decides the tariff and the net-metering steps." },
];

/** Error for the current step, or null when it can move on. */
export function stepError(step: Step, answers: Answers): string | null {
  if (step.key === "monthly_units_kwh") return checkMonthlyUnits(answers.monthly_units_kwh);
  return answers[step.key] ? null : "Choose one option.";
}

export function toRequest(answers: Answers, displayName: string | null): Schemas["CreateUserRequest"] | null {
  const { property_type, has_roof_rights, discom } = answers;
  if (!property_type || !has_roof_rights || !discom || checkMonthlyUnits(answers.monthly_units_kwh)) return null;
  return {
    display_name: displayName,
    property_type,
    has_roof_rights: has_roof_rights === "yes",
    monthly_units_kwh: Number(answers.monthly_units_kwh),
    discom,
  };
}

/** Prefill the card from a saved profile, for "Change my answers". */
export function answersFrom(user: Schemas["UserSummary"]): Answers {
  return {
    property_type: user.property_type,
    has_roof_rights: user.has_roof_rights ? "yes" : "no",
    monthly_units_kwh: String(user.monthly_units_kwh),
    discom: user.discom,
  };
}

export function labelOf<V extends string>(options: Option<V>[], value: V): string {
  return options.find((o) => o.value === value)?.label ?? value;
}
