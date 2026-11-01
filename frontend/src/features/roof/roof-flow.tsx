"use client";

import { RequireProfile } from "@/components/require-profile";

import { LocateHouse } from "./locate-house";

/** /roof: pin the house, then trace the roof. */
export function RoofFlow() {
  return <RequireProfile>{(userId) => <LocateHouse userId={userId} />}</RequireProfile>;
}
