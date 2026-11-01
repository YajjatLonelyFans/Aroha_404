import Link from "next/link";

import { buttonClass } from "@/components/ui/button";
import { RoofPreview } from "@/features/landing/roof-preview";

export default function Home() {
  return (
    <section className="mx-auto grid w-full max-w-6xl flex-1 items-center gap-12 px-6 py-12 lg:grid-cols-[1fr_1.1fr] lg:gap-16 lg:py-16">
      <div className="flex flex-col items-start gap-6">
        <h1 className="text-4xl leading-[1.08] sm:text-5xl">From your roof to your solar subsidy, step by step</h1>
        <p className="max-w-xl text-lg text-muted-foreground">
          Aroha checks your roof, estimates what panels could generate from ten years of weather data, works out
          cost, subsidy and payback, and walks you through the application.
        </p>
        <div className="flex flex-col items-start gap-3">
          <Link href="/start" className={buttonClass("primary", "h-12 px-6 text-base")}>
            Check my roof
          </Link>
          {/* Coverage is stated plainly: pins, tariffs, schemes and DISCOM steps are Delhi's for now. */}
          <p className="text-sm text-muted-foreground">Available for homes in Delhi today</p>
        </div>
      </div>
      <RoofPreview />
    </section>
  );
}
