"use client";

import { useMemoryEnabled } from "@/lib/memory-pref";
import { useSession } from "@/lib/session";
import { cn } from "@/lib/utils";

/** Header badge: "Memory ON" (forest) / "Memory OFF" (grey). Click to switch (DESIGN_SYSTEM "Meko badge"). */
export function MemoryToggle() {
  const session = useSession();
  const userId = session?.userId ?? null;
  const [enabled, setEnabled] = useMemoryEnabled(userId);
  if (!userId) return null;
  return (
    <button
      type="button"
      aria-pressed={enabled}
      onClick={() => setEnabled(!enabled)}
      title={enabled ? "The assistant remembers you between chats. Click to turn off." : "Each chat starts fresh. Click to turn memory on."}
      className={cn(
        "whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
        enabled ? "border-primary bg-primary text-primary-foreground" : "border-muted-foreground bg-card text-muted-foreground",
      )}
    >
      Memory {enabled ? "ON" : "OFF"}
    </button>
  );
}
