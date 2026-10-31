"""Remove homeowners and everything tied to them, for a clean demo database.

Usage (from backend/, venv active):
    python -m scripts.cleanup_users                 # dry run: list every homeowner, delete nothing
    python -m scripts.cleanup_users --apply         # delete ALL homeowners
    python -m scripts.cleanup_users --apply --user-id <id> [--user-id <id> ...]   # delete only these

Deletes from MongoDB: users, properties, roof_assessments, solar_estimates,
applications, agent_logs; and each user's Meko memories. Keeps the weather cache,
policy records, procedures and the shared lessons. Deletion cannot be undone.
"""

import argparse
import asyncio
import sys

from bson import ObjectId

from app.agents.contracts import AgentName
from app.core.settings import get_settings, is_configured
from app.db import collections as c
from app.db.client import create_client
from app.integrations.meko.base import MemoryUnavailable, agent_key
from app.integrations.meko.mcp_client import MekoMcpProvider

USER_COLLECTIONS = (c.PROPERTIES, c.ROOF_ASSESSMENTS, c.SOLAR_ESTIMATES, c.APPLICATIONS, c.AGENT_LOGS)
AGENTS: tuple[AgentName, ...] = ("roof", "weather", "financial", "policy", "application")


async def main(apply: bool, only: list[str]) -> int:
    s = get_settings()
    mongo = create_client(s)
    if mongo is None:
        print("MONGODB_URI is not set.")
        return 1
    db = mongo[s.mongodb_db]
    query = {"_id": {"$in": [ObjectId(u) for u in only]}} if only else {}
    users = [u async for u in db[c.USERS].find(query).sort("created_at", 1)]

    print(f"{'DELETING' if apply else 'DRY RUN (nothing deleted)'}: {len(users)} homeowner(s)")
    for u in users:
        uid = str(u["_id"])
        counts = {col: await db[col].count_documents({"user_id": uid}) for col in USER_COLLECTIONS}
        print(f"  {uid}  {str(u.get('display_name') or '(no name)'):18} created {u['created_at']:%Y-%m-%d %H:%M}  "
              + " ".join(f"{col}={n}" for col, n in counts.items() if n)
              + ("  +meko memories" if u.get("meko_conversation_id") else ""))

    if not apply:
        print("\nRun again with --apply to delete these.")
        await mongo.close()
        return 0

    memory = MekoMcpProvider(s.meko_mcp_url, s.meko_api_key, s.meko_datapack) if is_configured(s.meko_api_key) else None
    for u in users:
        uid, conv = str(u["_id"]), u.get("meko_conversation_id")
        if conv and memory is not None:
            try:
                async with memory.session() as ms:
                    dp = await ms.datapack_id()
                    for agent in AGENTS:
                        await ms._call("memory_delete_all", {"conversation_id": conv, "agent_id": agent_key(agent),
                                                             "run_id": conv, "datapack_id": dp})
            except MemoryUnavailable as exc:
                print(f"  {uid}: Meko memories NOT deleted ({exc.message}); MongoDB records kept so you can retry")
                continue
        for col in USER_COLLECTIONS:
            await db[col].delete_many({"user_id": uid})
        await db[c.USERS].delete_one({"_id": u["_id"]})
        print(f"  deleted {uid}")
    await mongo.close()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="actually delete (default is a dry run)")
    parser.add_argument("--user-id", action="append", default=[], help="limit to these user ids")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.apply, args.user_id)))
