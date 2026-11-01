import type { Metadata } from "next";

import { StartFlow } from "@/features/qualify/start-flow";

export const metadata: Metadata = { title: "A few questions · Aroha" };

export default function StartPage() {
  return (
    <section className="flex flex-1 items-start justify-center px-4 py-10 sm:items-center">
      <StartFlow />
    </section>
  );
}
