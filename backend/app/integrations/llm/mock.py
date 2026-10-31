"""Mock LLM for offline development. Its replies are labelled and only repeat the given facts."""

from app.integrations.llm.base import LLMReply

FACTS_HEADER = "FACTS"


class MockLLM:
    is_mock = True
    model = "mock-llm"

    async def generate(
        self, *, system: str, prompt: str, max_output_tokens: int = 700, temperature: float = 0.2
    ) -> LLMReply:
        facts = []
        if FACTS_HEADER in prompt:
            for line in prompt.split(FACTS_HEADER, 1)[1].splitlines():
                if line.startswith("- "):
                    facts.append(line[2:].strip())
        text = "(Mock assistant, not a live model) " + (" ".join(facts[:6]) or "I have no details yet.")
        return LLMReply(text=text, model=self.model, is_mock=True)
