import Image from "next/image";
import Link from "next/link";

import { buttonClass } from "@/components/ui/button";

// Placeholder landing page for F1; replaced when the screen designs arrive.
export default function Home() {
  return (
    <section className="mx-auto flex w-full max-w-3xl flex-1 flex-col items-center justify-center gap-6 px-4 py-16 text-center">
      <Image src="/brand/AROHA_Symbol_Full_Color.svg" alt="" width={96} height={96} priority />
      <p className="font-heading text-sm font-medium tracking-[0.3em] text-primary">RISE WITH THE SUN.</p>
      <h1 className="text-3xl sm:text-4xl">Is your Delhi roof ready for solar?</h1>
      <p className="max-w-xl text-lg text-muted-foreground">
        Aroha checks your roof, estimates what panels could generate from ten years of weather data, works out
        cost, subsidy and payback, and walks you through the application.
      </p>
      <Link href="/start" className={buttonClass("primary", "mt-2")}>
        Check my roof
      </Link>
    </section>
  );
}
