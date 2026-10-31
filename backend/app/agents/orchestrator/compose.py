"""Prompt for the single LLM call per turn, and the template reply used when the LLM is off or fails."""

from app.agents.contracts import AgentOutput
from app.integrations.meko.base import MemoryHit
from app.integrations.llm.mock import FACTS_HEADER

SYSTEM_PROMPT = """You are Aroha, a rooftop-solar assistant for homeowners in Delhi.
Reply in plain, warm, specific English in 3 to 6 sentences.
Use ONLY the facts and remembered notes you are given.
Copy every number exactly as written there: same digits, same rounding, same units.
Never calculate, round, convert, estimate or invent a number.
Say "estimate", "about" or "range"; never say "guaranteed", "approved" or "you will save".
If the facts do not answer the question, say what is missing and which step of the app provides it.
If the facts include a "Verified tip shared by Aroha" that is relevant, pass it on in one sentence.
Never mention coordinates, addresses, phone numbers or ID numbers."""

STRICT_RETRY = (
    "\n\nYour previous draft used numbers that are not in the facts ({numbers}). "
    "Rewrite it using only numbers copied exactly from the facts, or no numbers at all."
)

NEW_SESSION_REPLY = (
    "I don't have your home's details in this session. To get started, tell me: is it an independent "
    "house or a builder floor, do you have the right to use the roof, roughly how many units you use "
    "a month, and which DISCOM supplies you? Then you can mark your roof on the map."
)


def build_prompt(message: str, outputs: list[AgentOutput], recalled: list[MemoryHit]) -> str:
    lines = [f"Homeowner's question: {message.strip()}", ""]
    if recalled:
        lines.append("What Aroha remembers about this homeowner from earlier sessions:")
        lines += [f"* {m.text}" for m in recalled]
        lines.append("")
    lines.append(f"{FACTS_HEADER} (from Aroha's calculations):")
    for o in outputs:
        lines += [f"- {fact}" for fact in o.facts]
    lines += ["", "Write the reply."]
    return "\n".join(lines)


def template_reply(outputs: list[AgentOutput], recalled: list[MemoryHit], greeting: bool, fresh: bool) -> str:
    """Deterministic reply from the same facts, used when the LLM is unavailable or fails validation.

    A fresh session (memory off or unreachable) with nothing to explain asks for the basics again."""
    facts = [f for o in outputs for f in o.facts]
    if not facts or (fresh and not any(o.status == "ok" for o in outputs)):
        return NEW_SESSION_REPLY
    opening = "Welcome back. Here is where things stand. " if greeting and recalled else "Here is what I have. "
    return opening + " ".join(facts)
