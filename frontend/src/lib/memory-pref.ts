// The Memory ON/OFF choice, per homeowner, in this browser. ON (the default) lets the assistant
// recall and save notes in Meko; OFF sends meko_enabled=false, so each chat starts fresh.
import { useCallback, useSyncExternalStore } from "react";

const key = (userId: string) => `aroha.memory.${userId}`;
const memory = new Map<string, string>(); // fallback when storage is blocked
const listeners = new Set<() => void>();

function read(k: string): string | null {
  try {
    return window.localStorage.getItem(k);
  } catch {
    return memory.get(k) ?? null;
  }
}

function write(k: string, v: string): void {
  try {
    window.localStorage.setItem(k, v);
  } catch {
    memory.set(k, v);
  }
}

function subscribe(onChange: () => void): () => void {
  listeners.add(onChange);
  window.addEventListener("storage", onChange);
  return () => {
    listeners.delete(onChange);
    window.removeEventListener("storage", onChange);
  };
}

/** [memory enabled, set it]. Enabled until the homeowner turns it off. */
export function useMemoryEnabled(userId: string | null): [boolean, (on: boolean) => void] {
  const enabled = useSyncExternalStore(
    subscribe,
    () => (userId ? read(key(userId)) !== "off" : true),
    () => true,
  );
  const set = useCallback(
    (on: boolean) => {
      if (!userId) return;
      write(key(userId), on ? "on" : "off");
      listeners.forEach((l) => l());
    },
    [userId],
  );
  return [enabled, set];
}
