import type { Metadata } from "next";

import { StatusView } from "@/features/status/status-view";

export const metadata: Metadata = { title: "Demo readiness · Aroha" };

export default function StatusPage() {
  return (
    <section className="flex flex-1 flex-col">
      <StatusView />
    </section>
  );
}
