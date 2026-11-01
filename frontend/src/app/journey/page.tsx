import type { Metadata } from "next";

import { JourneyFlow } from "@/features/journey/journey-flow";

export const metadata: Metadata = { title: "Subsidies and next steps · Aroha" };

export default function JourneyPage() {
  return (
    <section className="flex flex-1 flex-col">
      <JourneyFlow />
    </section>
  );
}
