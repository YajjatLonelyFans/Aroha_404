"use client";

import { useEffect, useState } from "react";

import { setAssistantOpen, useAssistantOpen } from "@/lib/assistant-store";
import { useMemoryEnabled } from "@/lib/memory-pref";
import { useSession } from "@/lib/session";
import { cn } from "@/lib/utils";

import { AgentLog } from "./agent-log";
import { ChatPanel } from "./chat-panel";
import { MemoryToggle } from "./memory-toggle";

/**
 * "Ask Aroha": a chat drawer below the header on every page once the homeowner has a profile, with an
 * agent log tab. The header button opens it. It lives in the root layout, so the conversation carries
 * over as the person moves between pages.
 */
export function AssistantLauncher() {
  const session = useSession();
  const userId = session?.userId ?? null;
  const [enabled] = useMemoryEnabled(userId);
  const open = useAssistantOpen();
  const [tab, setTab] = useState<"chat" | "log">("chat");
  const [replies, setReplies] = useState(0);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setAssistantOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  if (!session || !userId) return null;

  return (
    <>
      {/* Stays mounted while closed, so a reply that arrives after closing is not lost. */}
      <aside
          aria-label="Aroha assistant"
          hidden={!open}
          className={cn(
            // Below the sticky header (h-16), so the header and its navigation stay usable.
            "fixed bottom-0 right-0 top-16 z-30 w-full flex-col border-l border-border bg-card shadow-[0_8px_24px_rgba(0,0,0,0.08)] sm:w-[420px]",
            open ? "flex" : "hidden",
          )}
        >
          <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
            <div className="flex items-center gap-2">
              <h2 className="text-lg">Ask Aroha</h2>
              <MemoryToggle />
            </div>
            <button
              type="button"
              onClick={() => setAssistantOpen(false)}
              aria-label="Close the assistant"
              className="rounded-md px-2 py-1 text-xl leading-none text-muted-foreground hover:bg-muted"
            >
              ×
            </button>
          </div>
          <div role="tablist" aria-label="Assistant views" className="flex border-b border-border px-2">
            {(["chat", "log"] as const).map((t) => (
              <button
                key={t}
                role="tab"
                type="button"
                aria-selected={tab === t}
                onClick={() => setTab(t)}
                className={cn(
                  "-mb-px border-b-2 px-3 py-2 text-sm font-medium",
                  tab === t ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground",
                )}
              >
                {t === "chat" ? "Chat" : "Agent log"}
              </button>
            ))}
          </div>
          {/* Both stay mounted so switching tabs keeps the conversation and the log. */}
          <div className={cn("min-h-0 flex-1 flex-col", tab === "chat" ? "flex" : "hidden")}>
            <ChatPanel key={userId} userId={userId} memoryEnabled={enabled} onReply={() => setReplies((n) => n + 1)} />
          </div>
          <div className={cn("min-h-0 flex-1 flex-col", tab === "log" ? "flex" : "hidden")}>
            {open && tab === "log" && <AgentLog userId={userId} refreshKey={replies} />}
          </div>
        </aside>
    </>
  );
}
