"use client";

import { RequireProfile } from "@/components/require-profile";

import { ResultsView } from "./results-view";

/** /results: generation, cost, subsidy, savings and payback. */
export function ResultsFlow() {
  return <RequireProfile>{(userId) => <ResultsView userId={userId} />}</RequireProfile>;
}
