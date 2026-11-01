"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";

import { BackendStatus } from "@/components/backend-status";
import { buttonClass } from "@/components/ui/button";
import { MemoryToggle } from "@/features/assistant/memory-toggle";
import { setAssistantOpen, useAssistantOpen } from "@/lib/assistant-store";
import { signOut, useSession } from "@/lib/session";
import { cn } from "@/lib/utils";

// The journey, in order. Shown once the homeowner has answered the questions.
const STEPS = [
  { href: "/start", label: "Your home" },
  { href: "/roof", label: "Roof" },
  { href: "/results", label: "Estimate" },
  { href: "/journey", label: "Subsidies" },
];

export function SiteHeader() {
  const session = useSession();
  const pathname = usePathname();
  const router = useRouter();
  const assistantOpen = useAssistantOpen();
  const [menu, setMenu] = useState(false);
  const hasProfile = Boolean(session?.userId);

  const leave = () => {
    setMenu(false);
    setAssistantOpen(false);
    signOut();
    router.push("/");
  };

  const stepLink = (step: (typeof STEPS)[number], block = false) => {
    const active = pathname === step.href;
    return (
      <Link
        key={step.href}
        href={step.href}
        onClick={() => setMenu(false)}
        aria-current={active ? "page" : undefined}
        className={cn(
          "rounded-md px-3 py-2 text-sm font-medium transition-colors",
          "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
          active ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
          block && "block",
        )}
      >
        {step.label}
      </Link>
    );
  };

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-card">
      <div className="mx-auto flex h-16 max-w-6xl items-center gap-4 px-4 md:gap-6">
        <Link href="/" aria-label="Aroha home" className="shrink-0">
          <Image src="/brand/AROHA_Horizontal_Full_Color.svg" alt="Aroha" width={125} height={32} priority />
        </Link>

        {hasProfile && (
          <nav aria-label="Your journey" className="hidden items-center gap-1 md:flex">
            {STEPS.map((step) => stepLink(step))}
          </nav>
        )}

        <div className="ml-auto flex items-center gap-2 sm:gap-3">
          <BackendStatus />
          {hasProfile && (
            <span className="hidden md:inline-flex">
              <MemoryToggle />
            </span>
          )}
          {hasProfile && (
            <button
              type="button"
              aria-expanded={assistantOpen}
              onClick={() => setAssistantOpen(!assistantOpen)}
              className={buttonClass(assistantOpen ? "primary" : "secondary", "h-9 whitespace-nowrap px-3 sm:px-4")}
            >
              Ask Aroha
            </button>
          )}
          {session === null && (
            <Link href="/login" className={buttonClass("ghost", "h-9 px-3")}>
              Sign in
            </Link>
          )}
          {session && (
            <div className={cn("items-center gap-1 text-sm", hasProfile ? "hidden md:flex" : "flex")}>
              <span className="hidden max-w-40 truncate text-muted-foreground lg:inline">{session.username}</span>
              <button type="button" onClick={leave} className={buttonClass("ghost", "h-9 whitespace-nowrap px-3")}>
                Sign out
              </button>
            </div>
          )}
          {hasProfile && (
            <button
              type="button"
              aria-expanded={menu}
              aria-controls="site-menu"
              onClick={() => setMenu(!menu)}
              className={buttonClass("ghost", "h-9 px-3 md:hidden")}
            >
              Menu
            </button>
          )}
        </div>
      </div>

      {hasProfile && menu && (
        <div id="site-menu" className="border-t border-border px-4 pb-4 pt-2 md:hidden">
          <nav aria-label="Your journey" className="flex flex-col">
            {STEPS.map((step) => stepLink(step, true))}
          </nav>
          <div className="mt-3 flex items-center justify-between border-t border-border pt-3">
            <MemoryToggle />
            <button type="button" onClick={leave} className={buttonClass("ghost", "h-9 px-3")}>
              Sign out
            </button>
          </div>
        </div>
      )}
    </header>
  );
}
