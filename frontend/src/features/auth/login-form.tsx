"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { ApiError, api } from "@/lib/api";
import { resumeHomeowner, signIn, useSession } from "@/lib/session";
import { checkEmail, checkPassword, checkUsername } from "@/lib/validation";

type Values = { email: string; username: string; password: string };
type Name = keyof Values;

const CHECKS: Record<Name, (value: string) => string | null> = {
  email: checkEmail,
  username: checkUsername,
  password: checkPassword,
};

const EMPTY: Values = { email: "", username: "", password: "" };
const UNTOUCHED: Record<Name, boolean> = { email: false, username: false, password: false };

/** Sign-in card. On /login it moves on to `redirectTo` once signed in; on /start it is shown in place. */
export function LoginForm({ redirectTo = "/start" }: { redirectTo?: string | null }) {
  const router = useRouter();
  const session = useSession();
  const [values, setValues] = useState<Values>(EMPTY);
  const [touched, setTouched] = useState(UNTOUCHED);

  // Already signed in: go straight on.
  useEffect(() => {
    if (session && redirectTo) router.replace(redirectTo);
  }, [session, redirectTo, router]);

  const errors = Object.fromEntries(
    (Object.keys(CHECKS) as Name[]).map((name) => [name, CHECKS[name](values[name])]),
  ) as Record<Name, string | null>;
  const shown = (name: Name) => (touched[name] ? errors[name] : null);

  const field = (name: Name) => ({
    value: values[name],
    error: shown(name),
    onChange: (e: React.ChangeEvent<HTMLInputElement>) => setValues((v) => ({ ...v, [name]: e.target.value })),
    onBlur: () => setTouched((t) => ({ ...t, [name]: true })),
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    setTouched({ email: true, username: true, password: true });
    if (errors.email || errors.username || errors.password) return;
    signIn(values.email, values.username); // the effect above navigates once the session is set
    // Next keeps a hidden page's state; clear it so the next person to sign in sees an empty form.
    setValues(EMPTY);
    setTouched(UNTOUCHED);
  }

  return (
    <Card className="w-full max-w-md">
      <h1 className="text-2xl">Sign in to continue</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Demo sign-in: any email works. Your details stay in this browser and your password is not stored.
      </p>
      <form className="mt-6 flex flex-col gap-4" onSubmit={submit} noValidate>
        <Field label="Email" type="email" autoComplete="email" inputMode="email" {...field("email")} />
        <Field label="Username" autoComplete="username" hint="3–20 letters, numbers, dots or underscores" {...field("username")} />
        <Field
          label="Password"
          type="password"
          autoComplete="current-password"
          hint="At least 8 characters, with a letter and a number"
          {...field("password")}
        />
        <Button type="submit" className="mt-2">
          Continue
        </Button>
      </form>
      <ResumeHomeowner />
    </Card>
  );
}

const HOMEOWNER_ID = /^[a-f0-9]{24}$/;

/** For the demo: continue as a homeowner seeded earlier (scripts/seed_demo.py prints the ID). */
function ResumeHomeowner() {
  const [id, setId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function resume(e: FormEvent) {
    e.preventDefault();
    const userId = id.trim().toLowerCase();
    if (!HOMEOWNER_ID.test(userId)) return setError("A homeowner ID is 24 letters and numbers (a–f, 0–9).");
    setBusy(true);
    setError(null);
    try {
      const user = await api("get", "/api/users/{user_id}", { path: { user_id: userId } });
      resumeHomeowner(userId, user.display_name?.trim() || "homeowner");
    } catch (err) {
      setError(err instanceof ApiError && err.status === 404 ? "No homeowner has that ID." : "Couldn't check that ID. Try again.");
      setBusy(false);
    }
  }

  return (
    <details className="mt-5 border-t border-border pt-4 text-sm">
      <summary className="cursor-pointer font-medium text-primary">Resume a saved homeowner</summary>
      <form onSubmit={resume} className="mt-3 flex flex-col gap-3" noValidate>
        <Field
          label="Homeowner ID"
          value={id}
          onChange={(e) => setId(e.target.value)}
          error={error}
          hint="From the demo seed script"
          autoComplete="off"
          spellCheck={false}
        />
        <Button type="submit" variant="secondary" disabled={busy} className="self-start">
          {busy ? "Checking…" : "Resume"}
        </Button>
      </form>
    </details>
  );
}
