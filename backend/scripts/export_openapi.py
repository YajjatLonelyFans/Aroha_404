"""Write the API schema to backend/openapi.json for the frontend's generated types.

Usage (from backend/, venv active):  python -m scripts.export_openapi
The frontend then runs openapi-typescript on this file to produce src/types/api.ts.
"""

import json
import sys

from app.core.settings import BACKEND_DIR, Settings
from app.main import create_app

OUT = BACKEND_DIR / "openapi.json"


def main() -> int:
    spec = create_app(Settings(_env_file=None)).openapi()
    OUT.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {OUT} ({len(spec['paths'])} paths, {len(spec.get('components', {}).get('schemas', {}))} schemas)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
