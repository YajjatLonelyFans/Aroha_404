"use client";

import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { MockBadge } from "@/components/mock-badge";
import { Button } from "@/components/ui/button";
import { ApiError, api, type Schemas } from "@/lib/api";
import { cn } from "@/lib/utils";

type Chat = Schemas["ChatResponse"];
export type Message =
  | { id: string; role: "user"; text: string }
  | { id: string; role: "assistant"; text: string; meta: Omit<Chat, "agent_outputs" | "reply"> }
  | { id: string; role: "error"; text: string };

const SUGGESTIONS = [
  "Hi, where was I?",
  "How does the monsoon affect my panels?",
  "What subsidy can I get?",
  "What should I do next?",
];

export const AGENT_LABELS: Record<string, string> = {
  roof: "Roof",
  weather: "Weather",
  financial: "Money",
  policy: "Subsidies",
  application: "Next steps",
};

const FALLBACK: Record<string, string> = {
  not_configured: "no AI model is set up",
  rate_limited: "the AI model is busy",
  unavailable: "the AI model is unavailable",
  invalid_numbers: "the AI reply used a number we couldn't check",
  no_facts: "there was nothing to look up yet",
};

const storageKey = (userId: string) => `aroha.chat.${userId}`;

function loadMessages(userId: string): Message[] {
  try {
    return JSON.parse(window.sessionStorage.getItem(storageKey(userId)) ?? "[]");
  } catch {
    return [];
  }
}

/** One conversation with Aroha. Every number in a reply comes from an agent's output (checked by the backend). */
export function ChatPanel({ userId, memoryEnabled, onReply }: { userId: string; memoryEnabled: boolean; onReply: () => void }) {
  const [messages, setMessages] = useState<Message[]>(() => loadMessages(userId));
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  // Keep the conversation for this browser tab (it survives page changes and reloads, not new tabs).
  useEffect(() => {
    try {
      window.sessionStorage.setItem(storageKey(userId), JSON.stringify(messages.slice(-40)));
    } catch {
      // storage blocked: the conversation just won't survive a reload
    }
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [messages, userId]);

  async function send(message: string) {
    const trimmed = message.trim();
    if (!trimmed || sending) return;
    setText("");
    setSending(true);
    const id = crypto.randomUUID();
    setMessages((m) => [...m, { id, role: "user", text: trimmed }]);
    try {
      const res = await api("post", "/api/assistant/chat", {
        body: { user_id: userId, message: trimmed, meko_enabled: memoryEnabled },
        timeoutMs: 60_000,
      });
      // Keep what the message footer needs; the agents' full outputs are not stored.
      const meta = { run_id: res.run_id, agents: res.agents, memory: res.memory, llm: res.llm, notes: res.notes,
        latency_ms: res.latency_ms, timings: res.timings };
      setMessages((m) => [...m, { id: `${id}-r`, role: "assistant", text: res.reply, meta }]);
      onReply();
    } catch (err) {
      let error = err instanceof ApiError ? err.message : "Something went wrong. Try again.";
      if (err instanceof ApiError && err.code === "rate_limited") {
        const wait = Number(err.details?.retry_after_s);
        error = `You're sending messages quickly. Try again${wait ? ` in about ${Math.ceil(wait)} seconds` : " shortly"}.`;
      }
      setMessages((m) => [...m, { id: `${id}-e`, role: "error", text: error }]);
    } finally {
      setSending(false);
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    void send(text);
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void send(text);
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div ref={listRef} className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-4" aria-live="polite">
        {messages.length === 0 && (
          <div className="flex flex-col gap-3">
            <p className="text-sm text-muted-foreground">
              Ask about your roof, the weather, costs, subsidies or what to do next. Answers use your saved details.
            </p>
            <div className="flex flex-wrap gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => void send(s)}
                  className="rounded-full border border-border px-3 py-1 text-sm hover:bg-muted"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m) =>
          m.role === "user" ? (
            <p key={m.id} className="max-w-[85%] self-end whitespace-pre-wrap rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground">
              {m.text}
            </p>
          ) : m.role === "error" ? (
            <p key={m.id} role="alert" className="rounded-md border border-danger px-3 py-2 text-sm text-danger">
              {m.text}
            </p>
          ) : (
            <AssistantMessage key={m.id} text={m.text} meta={m.meta} />
          ),
        )}
        {sending && (
          <p className="text-sm text-muted-foreground" role="status">
            Aroha is thinking…{memoryEnabled ? " Recalling what it knows about you can take about 15 seconds." : ""}
          </p>
        )}
      </div>

      <form onSubmit={submit} className="flex items-end gap-2 border-t border-border p-3">
        <label htmlFor="chat-input" className="sr-only">
          Message Aroha
        </label>
        <textarea
          id="chat-input"
          rows={2}
          maxLength={2000}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Ask Aroha…"
          className="min-h-11 flex-1 resize-none rounded-md border border-border bg-card px-3 py-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/20"
        />
        <Button type="submit" disabled={sending || !text.trim()}>
          Send
        </Button>
      </form>
    </div>
  );
}

function AssistantMessage({ text, meta }: { text: string; meta: Extract<Message, { role: "assistant" }>["meta"] }) {
  const mem = meta.memory;
  const memoryLine = !mem.enabled
    ? "Memory off: started fresh"
    : mem.error
      ? `Memory unavailable: ${mem.error}`
      : `Remembered ${mem.recalled} note${mem.recalled === 1 ? "" : "s"} about you${mem.shared ? ` and ${mem.shared} shared tip${mem.shared === 1 ? "" : "s"}` : ""}${mem.written ? `; saving ${mem.written} new` : ""}`;
  return (
    <div className="flex max-w-[92%] flex-col gap-1.5 self-start">
      <p className="whitespace-pre-wrap rounded-lg bg-muted px-3 py-2 text-sm">{text}</p>
      <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
        {meta.agents.map((a) => (
          <span key={a} className="rounded-full border border-border px-2 py-0.5">
            {AGENT_LABELS[a] ?? a}
          </span>
        ))}
        {(mem.is_mock && mem.enabled) && <MockBadge what="memory" />}
        {meta.llm.is_mock && <MockBadge what="assistant" />}
      </div>
      <p className={cn("text-xs", mem.error ? "text-warning" : "text-muted-foreground")}>
        {memoryLine}
        {!meta.llm.used && meta.llm.fallback_reason && ` · Template reply: ${FALLBACK[meta.llm.fallback_reason] ?? meta.llm.fallback_reason}`}
      </p>
      {meta.notes.length > 0 && (
        <ul className="list-disc pl-4 text-xs text-muted-foreground">
          {meta.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
