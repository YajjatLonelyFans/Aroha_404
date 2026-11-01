import Image from "next/image";
import Link from "next/link";

import { AccountMenu } from "@/components/account-menu";
import { BackendStatus } from "@/components/backend-status";
import { MemoryToggle } from "@/features/assistant/memory-toggle";

export function SiteHeader() {
  return (
    <header className="border-b border-border bg-card">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-4">
        <Link href="/" aria-label="Aroha home" className="shrink-0">
          <Image src="/brand/AROHA_Horizontal_Full_Color.svg" alt="Aroha" width={125} height={32} priority />
        </Link>
        <div className="flex items-center gap-3">
          <BackendStatus />
          <MemoryToggle />
          <AccountMenu />
        </div>
      </div>
    </header>
  );
}
