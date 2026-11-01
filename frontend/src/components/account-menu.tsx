"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { Button, buttonClass } from "@/components/ui/button";
import { signOut, useSession } from "@/lib/session";

export function AccountMenu() {
  const session = useSession();
  const router = useRouter();

  if (session === undefined) return null; // not read yet
  if (session === null) {
    return (
      <Link href="/login" className={buttonClass("ghost", "h-9 px-3")}>
        Sign in
      </Link>
    );
  }
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="hidden text-muted-foreground sm:inline">
        Signed in as <span className="font-medium text-foreground">{session.username}</span>
      </span>
      <Button
        variant="ghost"
        className="h-9 whitespace-nowrap px-3"
        onClick={() => {
          signOut();
          router.push("/");
        }}
      >
        Sign out
      </Button>
    </div>
  );
}
