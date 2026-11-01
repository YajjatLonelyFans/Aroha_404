"use client";

import { useCallback, useState } from "react";

import { LoginForm } from "@/features/auth/login-form";
import type { Schemas } from "@/lib/api";
import { linkUser, useSession, type Session } from "@/lib/session";

import { QualifyCard } from "./qualify-card";
import { QualifySummary } from "./qualify-summary";
import { EMPTY_ANSWERS, answersFrom, type Answers } from "./questions";

/**
 * /start: signed-out visitors sign in here, in place (a redirect would race the header's
 * "Sign out → home"). New people answer the questions; people with saved answers see them.
 */
export function StartFlow() {
  const session = useSession();
  if (session === undefined) return null; // not read yet
  if (session === null) return <LoginForm redirectTo={null} />;
  // Keyed by person: Next keeps this page's state across sign-out, and one person's
  // half-edited answers must never show up for the next.
  return <Journey key={session.email} session={session} />;
}

function Journey({ session }: { session: Session }) {
  // Answers being edited, and whether Cancel can go back to a saved profile.
  const [editing, setEditing] = useState<{ answers: Answers; cancelable: boolean } | null>(null);
  const [justSubmitted, setJustSubmitted] = useState(false);

  const changeAnswers = useCallback((user: Schemas["UserSummary"] | null) => {
    setEditing(user ? { answers: answersFrom(user), cancelable: true } : { answers: EMPTY_ANSWERS, cancelable: false });
  }, []);

  if (!session.userId || editing) {
    return (
      <QualifyCard
        displayName={session.username}
        initial={editing?.answers ?? EMPTY_ANSWERS}
        onCancel={editing?.cancelable ? () => setEditing(null) : undefined}
        onSubmitted={(userId) => {
          linkUser(userId);
          setEditing(null);
          setJustSubmitted(true);
        }}
      />
    );
  }
  return (
    <QualifySummary
      userId={session.userId}
      username={session.username}
      returning={!justSubmitted}
      onChangeAnswers={changeAnswers}
    />
  );
}
