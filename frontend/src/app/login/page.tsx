import type { Metadata } from "next";

import { LoginForm } from "@/features/auth/login-form";

export const metadata: Metadata = { title: "Sign in · Aroha" };

export default function LoginPage() {
  return (
    <section className="flex flex-1 items-center justify-center px-4 py-12">
      <LoginForm />
    </section>
  );
}
