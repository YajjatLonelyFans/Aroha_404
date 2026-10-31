"""Promote the verified lessons in seed/procedures.json to Meko's shared knowledge base.

Usage (from backend/, venv active):  python -m scripts.promote_lessons
Safe to run again: lessons that are already shared are skipped.
"""

import asyncio
import sys

from app.core.settings import get_settings, is_configured
from app.db.seed import load_procedures
from app.integrations.meko.mcp_client import MekoMcpProvider
from app.services.knowledge_service import promote_lessons


async def main() -> int:
    s = get_settings()
    if not is_configured(s.meko_api_key):
        print("MEKO_API_KEY is not set in .env")
        return 1
    lessons = [lesson for p in load_procedures() for lesson in p.lessons]
    report = await promote_lessons(MekoMcpProvider(s.meko_mcp_url, s.meko_api_key, s.meko_datapack), lessons)
    for text in report.promoted:
        print(f"PROMOTED: {text}")
    for text in report.already_shared:
        print(f"already shared: {text[:100]}...")
    for text, reason in report.rejected:
        print(f"REJECTED ({reason}): {text[:100]}...")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
