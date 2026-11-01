// Whether the "Ask Aroha" drawer is open. Shared by the header button, the drawer and the main
// area (which makes room for the drawer on wide screens instead of being covered by it).
import { useSyncExternalStore } from "react";

let open = false;
const listeners = new Set<() => void>();

export function setAssistantOpen(next: boolean): void {
  if (open === next) return;
  open = next;
  listeners.forEach((listener) => listener());
}

function subscribe(onChange: () => void): () => void {
  listeners.add(onChange);
  return () => listeners.delete(onChange);
}

export function useAssistantOpen(): boolean {
  return useSyncExternalStore(subscribe, () => open, () => false);
}
