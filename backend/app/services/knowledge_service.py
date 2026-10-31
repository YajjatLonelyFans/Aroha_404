"""Promote verified, de-identified lessons into Meko's shared knowledge base.

A lesson is promoted only if it has a source and a verified-on date and passes
the privacy filter. Promotion is one-way, so it is skipped when the same text
is already shared.
"""

from dataclasses import dataclass

from app.agents.orchestrator.privacy import privacy_problem
from app.db.seed import Lesson
from app.integrations.meko.base import MemoryProvider, agent_key

SHARED_SESSION = "shared-lessons"  # conversation that owns lessons before promotion


@dataclass
class PromotionReport:
    promoted: list[str]
    already_shared: list[str]
    rejected: list[tuple[str, str]]  # (lesson, reason)


async def promote_lessons(memory: MemoryProvider, lessons: list[Lesson]) -> PromotionReport:
    report = PromotionReport([], [], [])
    async with memory.session() as ms:
        conversation_id = await ms.ensure_conversation(SHARED_SESSION, None)
        for lesson in lessons:
            if not lesson.source_url or not lesson.verified_on:
                report.rejected.append((lesson.text, "needs a source and a verified-on date"))
                continue
            problem = privacy_problem(lesson.text)
            if problem:
                report.rejected.append((lesson.text, f"contains {problem}"))
                continue
            existing = await ms.shared_search(conversation_id, lesson.text, k=5)
            if any(hit.text.strip() == lesson.text.strip() for hit in existing):
                report.already_shared.append(lesson.text)
                continue
            agent = agent_key("application")
            memory_id = await ms.add(conversation_id, agent, lesson.text,
                                     {"kind": "lesson", "verified": True, "source_url": lesson.source_url,
                                      "verified_on": lesson.verified_on})
            if memory_id:
                await ms.promote(conversation_id, [memory_id], agent)
                report.promoted.append(lesson.text)
    return report
