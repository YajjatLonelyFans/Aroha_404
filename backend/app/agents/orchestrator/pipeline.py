"""One chat turn: recall → plan → run agents → compose → validate → (after the reply) commit.

Memory ON: the user's saved records and Meko memories are used, so a returning
homeowner is not asked again. Memory OFF: the turn is stateless, so the same
homeowner is asked for their details. If Meko fails, the turn continues as OFF
and says so.
"""

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from app.agents import application, financial, policy, roof, weather
from app.agents.contracts import AgentContext, AgentName, AgentOutput, MemoryCandidate
from app.agents.orchestrator.compose import STRICT_RETRY, SYSTEM_PROMPT, build_prompt, template_reply
from app.agents.orchestrator.privacy import privacy_problem
from app.agents.orchestrator.reply_validator import unknown_numbers
from app.agents.orchestrator.routing import RECALL_TOPICS, SHARED_TOPIC, plan, wants_forecast
from app.core.errors import AppError, NotFoundError
from app.db import collections as c
from app.db.store import DocumentStore
from app.integrations.llm.base import LLMProvider, LLMRateLimited, LLMUnavailable
from app.integrations.meko.base import MemoryHit, MemoryProvider, MemoryUnavailable, agent_key
from app.schemas.assistant import ChatRequest, ChatResponse, LLMInfo, MemoryInfo
from app.services.application_service import ApplicationService
from app.services.policy_service import PolicyService
from app.services.weather_service import WeatherService, utc_now

log = logging.getLogger(__name__)

CommitJob = Callable[[], Awaitable[None]]


class Orchestrator:
    def __init__(
        self,
        store: DocumentStore,
        weather: WeatherService,
        llm: LLMProvider | None,
        memory: MemoryProvider | None,
        policy: PolicyService,
        applications: ApplicationService,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._store = store
        self._weather = weather
        self._policy = policy
        self._applications = applications
        self._llm = llm
        self._memory = memory
        self._clock = clock

    async def chat(self, req: ChatRequest) -> tuple[ChatResponse, CommitJob | None]:
        started = time.perf_counter()
        run_id = uuid.uuid4().hex
        user = await self._store.get(c.USERS, req.user_id)
        if user is None:
            raise NotFoundError("User")

        agents = plan(req.message)
        notes: list[str] = []
        mem = MemoryInfo(enabled=req.meko_enabled, live=False,
                         is_mock=bool(self._memory and self._memory.is_mock), recalled=0, written=0)
        meko_calls: list[dict[str, Any]] = []
        recalled: list[MemoryHit] = []
        shared: list[MemoryHit] = []
        conversation_id: str | None = None

        # 1. Recall (Memory ON only).
        use_memory = req.meko_enabled
        if use_memory and self._memory is None:
            use_memory, mem.error = False, "Memory is not configured."
            notes.append("Memory is not set up, so this chat starts fresh.")
        elif use_memory:
            try:
                async with self._memory.session() as ms:
                    try:
                        conversation_id = await ms.ensure_conversation(req.user_id, user.get("meko_conversation_id"))
                        if conversation_id != user.get("meko_conversation_id"):
                            await self._store.update(c.USERS, req.user_id, {"meko_conversation_id": conversation_id})
                        queries = {agent_key(a): f"{req.message} ({RECALL_TOPICS[a]})" for a in agents}
                        if {"policy", "application"} & set(agents):
                            # Promoted lessons from the shared knowledge base, searched alongside recall.
                            recalled, shared = await asyncio.gather(
                                ms.search(conversation_id, queries, k=3),
                                self._shared_lessons(ms, conversation_id, f"{req.message} ({SHARED_TOPIC})"),
                            )
                        else:
                            recalled = await ms.search(conversation_id, queries, k=3)
                    finally:
                        meko_calls += [call.__dict__ for call in ms.calls]
                mem.live = any(call["ok"] for call in meko_calls) and not self._memory.is_mock
                mem.recalled, mem.shared = len(recalled), len(shared)
            except MemoryUnavailable as exc:
                use_memory, mem.error = False, exc.message
                notes.append("Memory is unavailable right now, so this chat starts fresh.")

        # 2. Context: saved records are only used when memory is on (resume).
        ctx = AgentContext(user_id=req.user_id, message=req.message, user=user,
                           wants_forecast=wants_forecast(req.message), resumed=use_memory)
        if use_memory:
            ctx.property = await self._store.latest(c.PROPERTIES, {"user_id": req.user_id})
            ctx.assessment = await self._store.latest(c.ROOF_ASSESSMENTS, {"user_id": req.user_id})
            ctx.estimate = await self._store.latest(c.SOLAR_ESTIMATES, {"user_id": req.user_id})
            ctx.application = await self._store.latest(c.APPLICATIONS, {"user_id": req.user_id})
            ctx.recalled = recalled
            ctx.shared_lessons = shared

        # 3. Run the chosen agents in parallel.
        outputs = await asyncio.gather(*[self._run_agent(a, ctx) for a in agents])

        # 4-5. Compose with one LLM call, validate numbers, fall back to the template.
        sources = [f for o in outputs for f in o.facts] + [m.text for m in recalled + shared] + [req.message]
        reply, llm_info = await self._compose(req.message, outputs, recalled, sources, fresh=not use_memory)

        # 6. Log the run; memory writes happen after the reply is sent.
        candidates = self._candidates(outputs, recalled, user) if use_memory and conversation_id else []
        mem.written = len(candidates)
        log_id = await self._store.insert(c.AGENT_LOGS, {
            "run_id": run_id,
            "user_id": req.user_id,
            "agents": list(agents),
            "status": "ok",
            "latency_ms": round(1000 * (time.perf_counter() - started)),
            "meko": {"enabled": req.meko_enabled, "live": mem.live, "is_mock": mem.is_mock,
                     "error": mem.error, "calls": meko_calls},
            "llm": llm_info.model_dump(),
            "is_mock": mem.is_mock or llm_info.is_mock,
            "created_at": self._clock(),
        })
        job = self._commit_job(conversation_id, candidates, log_id, user) if candidates else None

        response = ChatResponse(
            run_id=run_id, reply=reply, agents=list(agents), agent_outputs=list(outputs),
            memory=mem, llm=llm_info, notes=notes,
        )
        return response, job

    async def _run_agent(self, agent: AgentName, ctx: AgentContext) -> AgentOutput:
        try:
            if agent == "roof":
                return await roof.run(ctx)
            if agent == "weather":
                return await weather.run(ctx, self._weather)
            if agent == "policy":
                return await policy.run(ctx, self._policy)
            if agent == "application":
                return await application.run(ctx, self._applications)
            return await financial.run(ctx)
        except AppError as exc:
            return AgentOutput(agent=agent, status="error", error=exc.message)
        except Exception:  # one failing agent must not break the turn
            log.exception("Agent %s failed", agent)
            return AgentOutput(agent=agent, status="error", error="Unexpected error.")

    @staticmethod
    async def _shared_lessons(ms, conversation_id: str, query: str) -> list[MemoryHit]:
        try:
            return await ms.shared_search(conversation_id, query, k=2)
        except MemoryUnavailable:
            return []  # tips are optional; recall still counts

    async def _compose(
        self, message: str, outputs: list[AgentOutput], recalled: list[MemoryHit], sources: list[str], fresh: bool
    ) -> tuple[str, LLMInfo]:
        greeting = len(outputs) > 1
        has_facts = any(o.status == "ok" for o in outputs)

        def fallback(reason: str | None, used: bool = False) -> tuple[str, LLMInfo]:
            return template_reply(outputs, recalled, greeting, fresh), LLMInfo(
                used=used, model=self._llm.model if self._llm else None,
                is_mock=bool(self._llm and self._llm.is_mock), fallback_reason=reason)

        if not has_facts:
            return fallback("no_facts")  # nothing to explain yet; save the quota
        if self._llm is None:
            return fallback("not_configured")

        prompt = build_prompt(message, outputs, recalled)
        for attempt in range(2):
            try:
                reply = await self._llm.generate(system=SYSTEM_PROMPT, prompt=prompt)
            except LLMRateLimited:
                return fallback("rate_limited")
            except LLMUnavailable:
                return fallback("unavailable")
            bad = unknown_numbers(reply.text, sources)
            if not bad:
                return reply.text, LLMInfo(used=True, model=reply.model, is_mock=reply.is_mock, fallback_reason=None)
            log.info("Reply had numbers not in the facts %s (attempt %d)", bad, attempt + 1)
            prompt += STRICT_RETRY.format(numbers=", ".join(f"{n:g}" for n in bad))
        return fallback("invalid_numbers", used=True)

    @staticmethod
    def _candidates(outputs: list[AgentOutput], recalled: list[MemoryHit], user: dict) -> list[MemoryCandidate]:
        """Agent proposals that pass the privacy filter and are not already remembered.

        "Already remembered" is checked against the list kept on the user record, not
        against recall, because semantic search can miss a stored summary."""
        known = set(user.get("meko_saved", []))
        known |= {saved_key(m.agent_id or "", m.metadata.get("record_id")) for m in recalled}
        out = []
        for o in outputs:
            for cand in o.memory_writes:
                problem = privacy_problem(cand.text, user.get("display_name"))
                if problem:
                    log.warning("Dropped a %s memory: contains %s", cand.agent, problem)
                    continue
                if saved_key(agent_key(cand.agent), cand.record_id) in known:
                    continue
                out.append(cand)
        return out

    def _commit_job(
        self, conversation_id: str, candidates: list[MemoryCandidate], log_id: str, user: dict
    ) -> CommitJob:
        async def commit() -> None:
            calls: list[dict] = []
            saved: list[str] = []
            try:
                async with self._memory.session() as ms:
                    try:
                        ids = await asyncio.gather(*[
                            ms.add(conversation_id, agent_key(cand.agent), cand.text,
                                   {"kind": cand.agent, "record_id": cand.record_id})
                            for cand in candidates
                        ], return_exceptions=True)
                        saved = [saved_key(agent_key(cand.agent), cand.record_id)
                                 for cand, mid in zip(candidates, ids) if isinstance(mid, str)]
                    finally:
                        calls = [call.__dict__ for call in ms.calls]
            except MemoryUnavailable as exc:
                calls.append({"tool": "session", "latency_ms": 0, "ok": False, "error": exc.message})
            await self._store.update(c.AGENT_LOGS, log_id, {"meko_commit_calls": calls})
            if saved:
                await self._store.update(c.USERS, user["id"], {"meko_saved": user.get("meko_saved", []) + saved})

        return commit


def saved_key(agent_id: str, record_id: str | None) -> str:
    return f"{agent_id}|{record_id}"
