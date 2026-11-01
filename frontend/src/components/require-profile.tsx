"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { buttonClass } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { LoginForm } from "@/features/auth/login-form";
import { useSession } from "@/lib/session";

/**
 * Journey pages need a signed-in person who has answered the qualifying questions.
 * Signed-out visitors sign in here, in place; people without answers are sent to /start.
 * `children` is keyed by person so nothing carries over between them.
 */
export function RequireProfile({ children }: { children: (userId: string) => ReactNode }) {
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
          <p className="mt-2 text-muted-foreground">Tell us about your home before we go further.</p>
          <Link href="/start" className={buttonClass("primary", "mt-6")}>
            Answer the questions
          </Link>
        </Card>
      </div>
    );
  }
  return <div key={`${session.email}:${session.userId}`} className="flex flex-1 flex-col">{children(session.userId)}</div>;
}
