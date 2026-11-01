"use client";

import { RequireProfile } from "@/components/require-profile";

import { JourneyView } from "./journey-view";

/** /journey: eligibility, next steps and the document checklist. */
export function JourneyFlow() {
  return <RequireProfile>{(userId) => <JourneyView userId={userId} />}</RequireProfile>;
}
