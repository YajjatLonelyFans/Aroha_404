"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { signIn, useSession } from "@/lib/session";
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
        <Field label="Username" autoComplete="username" hint="3–20 letters, numbers, dots or underscores." {...field("username")} />
        <Field
          label="Password"
          type="password"
          autoComplete="current-password"
          hint="At least 8 characters, with a letter and a number."
          {...field("password")}
        />
        <Button type="submit" className="mt-2">
          Continue
        </Button>
      </form>
    </Card>
  );
}
