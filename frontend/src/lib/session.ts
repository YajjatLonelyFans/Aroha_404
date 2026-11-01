// Demo sign-in, kept in this browser only. Nothing is sent to the backend and the password
// is never stored. Signing in again with the same email in the same browser reconnects to
// that person's saved answers (their backend user id).
import { useSyncExternalStore } from "react";

export type Session = { email: string; username: string; userId: string | null };

const SESSION_KEY = "aroha.session";
const KNOWN_KEY = "aroha.known-users"; // email -> backend user id

// Storage can throw (private windows, blocked site data); fall back to memory for this tab.
const memory = new Map<string, string>();

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return memory.get(key) ?? null;
  }
}

function write(key: string, value: string | null): void {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    if (value === null) memory.delete(key);
    else memory.set(key, value);
  }
}

function parseSession(raw: string | null): Session | null {
  if (!raw) return null;
  try {
    const s = JSON.parse(raw);
    if (typeof s?.email !== "string" || typeof s?.username !== "string") return null;
    return { email: s.email, username: s.username, userId: typeof s.userId === "string" ? s.userId : null };
  } catch {
    return null;
  }
}

function readKnown(): Record<string, string> {
  try {
    const known = JSON.parse(read(KNOWN_KEY) ?? "{}");
    return known && typeof known === "object" ? known : {};
  } catch {
    return {};
  }
}

const listeners = new Set<() => void>();
const emit = () => listeners.forEach((listener) => listener());

// useSyncExternalStore needs the same object back while nothing has changed.
let cachedRaw: string | null | undefined;
let cachedSession: Session | null = null;

export function getSession(): Session | null {
  const raw = read(SESSION_KEY);
  if (raw !== cachedRaw) {
    cachedRaw = raw;
    cachedSession = parseSession(raw);
  }
  return cachedSession;
}

export function signIn(email: string, username: string): Session {
  const key = email.trim().toLowerCase();
  const session: Session = { email: key, username: username.trim(), userId: readKnown()[key] ?? null };
  write(SESSION_KEY, JSON.stringify(session));
  emit();
  return session;
}

export function signOut(): void {
  write(SESSION_KEY, null);
  emit();
}

/** Remember the backend user created by the qualifying answers, for this session and future sign-ins. */
export function linkUser(userId: string): void {
  const session = getSession();
  if (!session) return;
  write(SESSION_KEY, JSON.stringify({ ...session, userId }));
  write(KNOWN_KEY, JSON.stringify({ ...readKnown(), [session.email]: userId }));
  emit();
}

function subscribe(onChange: () => void): () => void {
  listeners.add(onChange);
  const onStorage = (e: StorageEvent) => {
    if (e.key === SESSION_KEY) onChange(); // signed in or out in another tab
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(onChange);
    window.removeEventListener("storage", onStorage);
  };
}

/** `undefined` until the browser storage has been read (server render, hydration), then the session or null. */
export function useSession(): Session | null | undefined {
  return useSyncExternalStore<Session | null | undefined>(subscribe, getSession, () => undefined);
}

/**
 * Sign in as a homeowner who already exists in the backend (e.g. the demo's seeded returning
 * homeowner, made by `python -m scripts.seed_demo`). Demo-grade, like the rest of this sign-in.
 */
export function resumeHomeowner(userId: string, username: string): Session {
  const session: Session = { email: `homeowner-${userId}@aroha.local`, username, userId };
  write(SESSION_KEY, JSON.stringify(session));
  write(KNOWN_KEY, JSON.stringify({ ...readKnown(), [session.email]: userId }));
  emit();
  return session;
}
