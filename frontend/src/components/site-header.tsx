import Image from "next/image";
import Link from "next/link";

import { BackendStatus } from "@/components/backend-status";

export function SiteHeader() {
  return (
    <header className="border-b border-border bg-card">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-4">
        <Link href="/" aria-label="Aroha home">
          <Image src="/brand/AROHA_Horizontal_Full_Color.svg" alt="Aroha" width={125} height={32} priority />
        </Link>
        <BackendStatus />
      </div>
    </header>
  );
}
