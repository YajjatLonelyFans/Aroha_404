"use client";

import type { ReactNode } from "react";

import { useAssistantOpen } from "@/lib/assistant-store";
import { cn } from "@/lib/utils";

/** The page body. On wide screens it makes room for the open "Ask Aroha" drawer instead of sitting under it. */
export function MainArea({ children }: { children: ReactNode }) {
  const assistantOpen = useAssistantOpen();
  return <main className={cn("flex flex-1 flex-col", assistantOpen && "xl:pr-[420px]")}>{children}</main>;
}
