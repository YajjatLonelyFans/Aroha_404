"""Application agent: next steps, missing documents and progress, plus shared verified tips."""

from app.agents.contracts import AgentContext, AgentOutput, MemoryCandidate
from app.services.application_service import NOTE, ApplicationService


async def run(ctx: AgentContext, applications: ApplicationService) -> AgentOutput:
    tips = [f"Verified tip shared by Aroha: {hit.text}" for hit in ctx.shared_lessons]
    if not ctx.resumed:
        return AgentOutput(agent="application", status="partial",
                           facts=["The application steps depend on your DISCOM, so your details are needed first."])

    app = ctx.application
    if app is None:
        procedure = await applications.procedure_for(ctx.user["discom"])
        if procedure is None:
            return AgentOutput(agent="application", status="partial",
                               facts=[f"No verified procedure is stored for {ctx.user['discom']} yet."] + tips)
        first = [s["title"] for s in procedure["steps"][:2]]
        facts = ["No application is being tracked yet; start one to get the full checklist.",
                 f"The first steps are: {' Then: '.join(first)}",
                 f"Steps are from the official Delhi procedure ({procedure['source_url']})."] + tips
        return AgentOutput(agent="application", status="ok", facts=facts,
                           result={"application_id": None, "first_steps": first})

    steps = app["steps"]
    done = sum(s["status"] == "done" for s in steps)
    todo = [s["title"] for s in steps if s["status"] != "done"][:2]
    missing = [d["label"] for d in app["documents"] if d["required"] and not d["provided"]]
    facts = [f"Application stage: {app['status']}; {done} of {len(steps)} steps marked done."]
    if todo:
        facts.append(f"Next: {' Then: '.join(todo)}")
    facts.append(f"Documents still needed: {', '.join(missing)}." if missing else "All required documents are marked provided.")
    facts.append(NOTE)
    facts += tips
    provided = sum(d["provided"] for d in app["documents"])
    return AgentOutput(
        agent="application",
        status="ok",
        result={"application_id": app["id"], "status": app["status"], "steps_done": done,
                "steps_total": len(steps), "missing_documents": missing},
        facts=facts,
        memory_writes=[MemoryCandidate(
            agent="application",
            record_id=f"{app['id']}|{done}|{provided}",
            text=(f"Application progress: stage {app['status']}, {done} of {len(steps)} steps done; "
                  f"documents pending: {', '.join(missing) or 'none'}."),
        )],
    )
