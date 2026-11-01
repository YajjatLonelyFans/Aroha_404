import type { Metadata } from "next";

import { ResultsFlow } from "@/features/solar/results-flow";

export const metadata: Metadata = { title: "Your solar estimate · Aroha" };

export default function ResultsPage() {
  return (
    <section className="flex flex-1 flex-col">
      <ResultsFlow />
    </section>
  );
}
