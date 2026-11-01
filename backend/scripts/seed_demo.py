"""Seed the demo's returning homeowner through the running API (live Meko, live Gemini).

Usage (from backend/, venv active, backend running on :8000):
    python -m scripts.seed_demo                    # create them; prints the homeowner ID
    python -m scripts.seed_demo --check <user_id>  # later: does memory recall them yet?

Run it at least 10 minutes before judging: Meko extracts memories in the background.
On the demo browser, open /login and use "Resume a saved homeowner" with the printed ID.

The persona follows docs/DEMO_SCRIPT.md (illustrative, not a real homeowner) and the roof
is drawn on a public building, the SSCBS campus, never a private home.
"""

import argparse
import math
import sys
import time

import httpx

API = "http://localhost:8000/api"
SSCBS = (28.7327, 77.1190)  # lat, lon (same spot scripts/warm_cache.py warms)
CHATS = [
    "I'd prefer the cheaper option, and I want to apply before winter.",
    "What subsidy can I get?",
]


def rect(lat: float, lon: float, east_m: float, north_m: float, dx_m: float = 0, dy_m: float = 0) -> dict:
    """A GeoJSON rectangle east_m × north_m, offset dx/dy metres from (lat, lon)."""
    m_lat = 1 / 110_574.0
    m_lon = 1 / (111_320.0 * math.cos(math.radians(lat)))
    x0, y0 = lon + dx_m * m_lon, lat + dy_m * m_lat
    x1, y1 = x0 + east_m * m_lon, y0 + north_m * m_lat
    return {"type": "Polygon", "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]}


def call(client: httpx.Client, method: str, path: str, **kwargs) -> dict:
    r = client.request(method, API + path, **kwargs)
    if r.status_code >= 400:
        sys.exit(f"{method} {path} failed ({r.status_code}): {r.text[:300]}")
    return r.json()


def seed() -> int:
    with httpx.Client(timeout=90) as c:
        user = call(c, "POST", "/users", json={
            "display_name": "Demo homeowner", "property_type": "independent_house",
            "has_roof_rights": True, "monthly_units_kwh": 350, "discom": "BRPL",
        })
        uid = user["user_id"]
        lat, lon = SSCBS
        prop = call(c, "POST", "/properties", json={"user_id": uid, "lat": lat, "lon": lon,
                                                    "address_text": "SSCBS campus, Rohini (public building)"})
        roof = call(c, "POST", "/roof/assess", json={
            "user_id": uid, "property_id": prop["property_id"], "roof_type": "flat",
            "outline": rect(lat, lon, 16, 12, -8, -6),
            "no_go_areas": [{"kind": "water_tank", "geometry": rect(lat, lon, 2.5, 2.5, 4, 2)}],
            "shading": {"east": "partial", "south": "none", "west": "none", "north": "none"},
        })
        est = call(c, "POST", "/solar/estimate", json={"user_id": uid, "assessment_id": roof["assessment_id"]})
        app = call(c, "POST", "/applications", json={"user_id": uid})
        call(c, "PATCH", f"/applications/{app['application_id']}",
             json={"user_id": uid, "step_id": "register", "step_status": "done"})
        call(c, "PATCH", f"/applications/{app['application_id']}",
             json={"user_id": uid, "document_type": "electricity_bill", "provided": True})
        print(f"Homeowner {uid}: {roof['panel_count']} panels fit, recommended {est['recommended_kwp']} kWp, "
              f"tracker started (1 step done, bill ready).")

        for message in CHATS:
            reply = call(c, "POST", "/assistant/chat", json={"user_id": uid, "message": message, "meko_enabled": True})
            mem = reply["memory"]
            print(f"  chat: {message!r} -> memory live={mem['live']}, saving {mem['written']} note(s)"
                  + (f", error: {mem['error']}" if mem["error"] else ""))
            time.sleep(2)

        # The saves run after each reply; wait until the log shows them.
        for _ in range(30):
            logs = call(c, "GET", "/assistant/logs", params={"user_id": uid, "limit": 5})["logs"]
            commits = [log["memory"]["commit_calls"] for log in logs]
            if all(cc is not None for cc in commits):
                ok = sum(1 for cc in commits for call_ in cc if call_["ok"] and call_["tool"] == "memory_add")
                print(f"  memories saved to Meko: {ok} memory_add call(s) succeeded")
                break
            time.sleep(2)
        else:
            print("  memories still saving; check the agent log in a minute")

    print()
    print(f"HOMEOWNER ID: {uid}")
    print("Wait at least 10 minutes (Meko extraction), then:")
    print(f"  python -m scripts.seed_demo --check {uid}")
    print("On the demo browser: /login -> 'Resume a saved homeowner' -> paste the ID.")
    return 0


def check(uid: str) -> int:
    with httpx.Client(timeout=90) as c:
        reply = call(c, "POST", "/assistant/chat", json={"user_id": uid, "message": "Hi, where was I?", "meko_enabled": True})
    mem = reply["memory"]
    print(f"Recalled {mem['recalled']} note(s) and {mem['shared']} shared tip(s); memory live={mem['live']}")
    if mem["error"]:
        print(f"Memory error: {mem['error']}")
    for note in reply["notes"]:
        print(f"Note: {note}")
    print(f"\nReply: {reply['reply']}")
    ready = mem["live"] and mem["recalled"] > 0
    print("\nREADY for the returning-user demo." if ready else "\nNOT READY yet: wait a few minutes and check again.")
    return 0 if ready else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # replies contain ₹; the Windows console default can't print it
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", metavar="USER_ID", help="check that memory recalls this homeowner")
    args = parser.parse_args()
    sys.exit(check(args.check) if args.check else seed())
