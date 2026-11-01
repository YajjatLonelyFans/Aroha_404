import type { Metadata } from "next";

import { RoofFlow } from "@/features/roof/roof-flow";

export const metadata: Metadata = { title: "Find your house · Aroha" };

export default function RoofPage() {
  return (
    <section className="flex flex-1 flex-col">
      <RoofFlow />
    </section>
  );
}
