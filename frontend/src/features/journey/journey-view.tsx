"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Button, buttonClass } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ApplicationTracker } from "@/features/applications/application-tracker";
import { SchemeList } from "@/features/subsidies/scheme-list";
import { ApiError, api, type Schemas } from "@/lib/api";

type Load =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | {
      kind: "ready";
      user: Schemas["UserSummary"];
      eligibility: Schemas["EligibilityResponse"];
      application: Schemas["ApplicationResponse"] | null;
    };

const message = (err: unknown) => (err instanceof ApiError ? err.message : "Something went wrong.");

/** Step 6: which schemes apply, and the application steps and documents (PRD FR-17 to FR-20). */
export function JourneyView({ userId }: { userId: string }) {
  const [load, setLoad] = useState<Load>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const ctrl = new AbortController();
    const { signal } = ctrl;
    (async () => {
      const user = await api("get", "/api/users/{user_id}", { path: { user_id: userId }, signal });
      const [eligibility, application] = await Promise.all([
        api("post", "/api/policy/eligibility", { body: { user_id: userId }, signal }),
        user.latest.application_id
          ? api("get", "/api/applications/{application_id}", {
              path: { application_id: user.latest.application_id },
              query: { user_id: userId },
              signal,
            })
          : Promise.resolve(null),
      ]);
      setLoad({ kind: "ready", user, eligibility, application });
    })().catch((err) => {
      if (!signal.aborted) setLoad({ kind: "error", message: message(err) });
    });
    return () => ctrl.abort();
  }, [userId, attempt]);

  if (load.kind === "loading") return <p className="p-6 text-muted-foreground">Checking schemes and steps…</p>;
  if (load.kind === "error") {
    return (
      <Card className="m-auto w-full max-w-md">
        <p role="alert" className="text-danger">
          {load.message}
        </p>
        <Button
          className="mt-4"
          onClick={() => {
            setLoad({ kind: "loading" });
            setAttempt((n) => n + 1);
          }}
        >
          Try again
        </Button>
      </Card>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-8 px-4 py-8">
      <header>
        <h1 className="text-3xl">Subsidies and next steps</h1>
        <p className="mt-2 text-muted-foreground">
          Which schemes fit your home, and what to do to get the panels approved and switched on
        </p>
      </header>

      <section aria-labelledby="schemes-title" className="flex flex-col gap-3">
        <h2 id="schemes-title" className="text-xl">
          Schemes for your home
        </h2>
        <SchemeList eligibility={load.eligibility} />
      </section>

      <Card className="flex flex-col gap-4">
        <h2 className="text-xl">Your application</h2>
        {load.application ? (
          <ApplicationTracker initial={load.application} userId={userId} />
        ) : (
          <StartTracking userId={userId} discom={load.user.discom} onStarted={(application) => setLoad({ ...load, application })} />
        )}
      </Card>

      <div className="flex flex-wrap gap-3">
        <Link href="/results" className={buttonClass("ghost")}>
          Back to my estimate
        </Link>
      </div>
    </div>
  );
}

function StartTracking({
  userId,
  discom,
  onStarted,
}: {
  userId: string;
  discom: string;
  onStarted: (application: Schemas["ApplicationResponse"]) => void;
}) {
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function start() {
    setStarting(true);
    setError(null);
    try {
      onStarted(await api("post", "/api/applications", { body: { user_id: userId } }));
    } catch (err) {
      setError(message(err));
      setStarting(false);
    }
  }

  return (
    <div className="flex flex-col items-start gap-3">
      <p className="text-muted-foreground">
        See every step for {discom === "other" ? "your electricity supplier" : discom}, from registering on the national
        portal to the subsidy reaching your bank, with a checklist of the documents you&apos;ll need. Aroha keeps track as
        you go; it does not apply for you.
      </p>
      {error && (
        <p role="alert" className="rounded-md border border-danger px-3 py-2 text-sm text-danger">
          {error}
        </p>
      )}
      <Button onClick={start} disabled={starting}>
        {starting ? "Starting…" : "Show my steps and checklist"}
      </Button>
    </div>
  );
}
