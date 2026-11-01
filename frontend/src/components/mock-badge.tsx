/** Visible label for any value that came from a mock adapter (CLAUDE.md rule 6). */
export function MockBadge({ what }: { what?: string }) {
  return (
    <span
      className="inline-flex items-center rounded-full border border-muted-foreground px-2 py-0.5 text-xs font-medium text-muted-foreground"
      title={what ? `${what} is using mock data, not a live service` : "Mock data, not a live service"}
    >
      Mock{what ? `: ${what}` : ""}
    </span>
  );
}
