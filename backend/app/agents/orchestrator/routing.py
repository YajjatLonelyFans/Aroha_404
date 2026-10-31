"""Pick agents with keyword rules, so routing costs no LLM call (free-tier quota is small)."""

import re

from app.agents.contracts import AgentName

KEYWORDS: dict[AgentName, tuple[str, ...]] = {
    "roof": ("roof", "panel", "area", "space", "fit", "shade", "shadow", "tank", "stair", "layout",
             "capacity", "how many", "size", "kw"),
    "weather": ("weather", "monsoon", "winter", "summer", "season", "rain", "cloud", "haze", "smog", "fog",
                "sun", "heat", "hot", "temperature", "forecast", "week", "today", "tomorrow", "month",
                "generat", "produce", "output", "kwh"),
    "financial": ("cost", "price", "save", "saving", "payback", "money", "bill", "rupee", "₹", "rs", "inr",
                  "afford", "worth", "subsidy", "loan", "emi", "recommend", "budget", "invest", "return"),
    "policy": ("subsid", "scheme", "eligib", "surya ghar", "government", "incentive", "gbi", "yojana", "qualify"),
    "application": ("apply", "applic", "document", "paper", "step", "next", "net meter", "discom", "process",
                    "register", "portal", "vendor", "inspect", "bank", "approval", "commission"),
}
# Added to the homeowner's message when recalling each agent's memories, so greetings
# like "where was I?" still match the stored summaries.
RECALL_TOPICS: dict[AgentName, str] = {
    "roof": "roof assessment usable area panels kW shade",
    "weather": "weather yearly output per kW sunniest month seasons",
    "financial": "estimate recommended size cost savings payback",
    "policy": "subsidy schemes eligible amounts",
    "application": "application progress steps documents pending",
}
SHARED_TOPIC = "Delhi rooftop solar subsidy application procedure DISCOM"
FORECAST_WORDS = ("forecast", "this week", "next week", "today", "tomorrow", "next few days", "coming days")
ALL_AGENTS: tuple[AgentName, ...] = ("roof", "weather", "financial", "policy", "application")


def _has(text: str, word: str) -> bool:
    if word.isalpha() and len(word) <= 3:
        return re.search(rf"\b{re.escape(word)}\b", text) is not None  # "rs", "kw" as whole words
    return word in text


def plan(message: str) -> list[AgentName]:
    """Agents the message needs; a greeting or unclear question gets all of them (a status summary)."""
    text = message.lower()
    chosen = [agent for agent, words in KEYWORDS.items() if any(_has(text, w) for w in words)]
    return chosen or list(ALL_AGENTS)


def wants_forecast(message: str) -> bool:
    text = message.lower()
    return any(w in text for w in FORECAST_WORDS)
