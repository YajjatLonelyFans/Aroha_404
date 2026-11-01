"use client";

import Link from "next/link";

import { buttonClass } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { LoginForm } from "@/features/auth/login-form";
import { useSession } from "@/lib/session";

import { LocateHouse } from "./locate-house";

/** /roof: needs a signed-in person who has answered the qualifying questions. */
export function RoofFlow() {
  const session = useSession();
  if (session === undefined) return null; // not read yet
  if (session === null) {
    return (
      <div className="flex flex-1 items-center justify-center px-4 py-12">
        <LoginForm redirectTo={null} />
      </div>
    );
  }
  if (!session.userId) {
    return (
      <div className="flex flex-1 items-center justify-center px-4 py-12">
        <Card className="w-full max-w-md">
          <h1 className="text-2xl">A few questions first</h1>
          <p className="mt-2 text-muted-foreground">Tell us about your home before finding it on the map.</p>
          <Link href="/start" className={buttonClass("primary", "mt-6")}>
            Answer the questions
          </Link>
        </Card>
      </div>
    );
  }
  // Keyed by person and profile so nothing carries over between them.
  return <LocateHouse key={`${session.email}:${session.userId}`} userId={session.userId} />;
}
