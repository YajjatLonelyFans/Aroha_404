"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Button, buttonClass } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ApiError, api, type Schemas } from "@/lib/api";
import { formatKwh } from "@/lib/format";

import { DISCOM_OPTIONS, PROPERTY_OPTIONS, labelOf } from "./questions";

type User = Schemas["UserSummary"];
type State = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ok"; user: User };

type Props = {
  userId: string;
  username: string;
  returning: boolean;
  onChangeAnswers: (user: User | null) => void;
};

/** The saved qualifying answers and whether the journey can continue. */
export function QualifySummary({ userId, username, returning, onChangeAnswers }: Props) {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const ctrl = new AbortController();
    api("get", "/api/users/{user_id}", { path: { user_id: userId }, signal: ctrl.signal })
      .then((user) => setState({ kind: "ok", user }))
      .catch((err) => {
        if (ctrl.signal.aborted) return;
        // The saved profile is gone (e.g. the demo database was cleaned): ask again.
        if (err instanceof ApiError && err.status === 404) return onChangeAnswers(null);
        setState({ kind: "error", message: err instanceof ApiError ? err.message : "Something went wrong." });
      });
    return () => ctrl.abort();
  }, [userId, attempt, onChangeAnswers]);

  if (state.kind === "loading") {
    return (
      <Card className="w-full max-w-xl" aria-busy="true">
        <p className="text-muted-foreground">Loading your answers…</p>
      </Card>
    );
  }
  if (state.kind === "error") {
    return (
      <Card className="w-full max-w-xl">
        <p role="alert" className="text-danger">
          {state.message}
        </p>
        <Button
          className="mt-4"
          onClick={() => {
            setState({ kind: "loading" });
            setAttempt((n) => n + 1);
          }}
        >
          Try again
        </Button>
      </Card>
    );
  }

  const { user } = state;
  return (
    <Card className="w-full max-w-xl">
      {returning && <p className="text-sm text-muted-foreground">Welcome back, {username}.</p>}
      {user.eligible_to_continue ? (
        <>
          <h1 className="mt-1 text-2xl">Your home can go on to the roof check</h1>
          <p className="mt-2 text-muted-foreground">
            Next, find your house on the satellite map and trace the roof. It takes a few minutes.
          </p>
        </>
      ) : (
        <>
          <h1 className="mt-1 text-2xl">Aroha can&apos;t take this home further yet</h1>
          <p className="mt-2">{user.reason}</p>
        </>
      )}

      <dl className="mt-6 grid grid-cols-1 gap-x-6 gap-y-3 rounded-md bg-muted p-4 text-sm sm:grid-cols-2">
        <Answer label="Home" value={labelOf(PROPERTY_OPTIONS, user.property_type)} />
        <Answer label="Use of the roof" value={user.has_roof_rights ? "Yes" : "No, or not sure"} />
        <Answer label="Monthly use" value={formatKwh(user.monthly_units_kwh)} />
        <Answer label="Electricity supplier" value={labelOf(DISCOM_OPTIONS, user.discom)} />
      </dl>

      <div className="mt-8 flex flex-wrap items-center justify-between gap-3">
        <Button variant={user.eligible_to_continue ? "ghost" : "primary"} onClick={() => onChangeAnswers(user)}>
          Change my answers
        </Button>
        {user.eligible_to_continue && (
          <Link href="/roof" className={buttonClass("primary")}>
            Find my roof
          </Link>
        )}
      </div>
    </Card>
  );
}

function Answer({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-medium tabular-nums">{value}</dd>
    </div>
  );
}
