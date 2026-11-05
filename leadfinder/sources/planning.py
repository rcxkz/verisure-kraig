"""New planning applications via PlanIt (planit.org.uk), which aggregates UK council planning portals.

Homeowners extending or converting are investing in the house; new-build estates mean
whole streets of new residents; change-of-use / shopfront / signage often means a new business.
"""
import re
from datetime import datetime, timezone

from ..geo import nearest_town
from ..http import get

API = "https://www.planit.org.uk/api/applics/json"

KINDS = [
    ("skip", re.compile(r"\b(tree|tpo|fell|pollard|prune|discharge of condition|non[- ]material|telecom|mast|"
                        r"lawful (existing|development).*(use|existing)|demolition only)\b", re.I)),
    ("new_homes", re.compile(r"\b(erection of|construction of|new build|proposed)\b.*\b(\d+|new|detached|semi|terrace)?\s*"
                             r"(dwelling|dwellings|houses|homes|flats|apartments|bungalows?)\b", re.I)),
    ("business", re.compile(r"\b(change of use|shop ?front|advertisement|signage|illuminated|class e|takeaway|"
                            r"hot food|restaurant|retail|commercial unit|business use)\b", re.I)),
    ("home_improvement", re.compile(r"\b(extension|loft|dormer|conservatory|porch|garage conversion|conversion of garage|"
                                    r"convert(ing)? (the )?garage|outbuilding|annex|annexe|single storey|two storey|"
                                    r"first floor|roof|summer ?house|garden room|driveway|dropped kerb|fence|gates?)\b", re.I)),
]
LABEL = {"home_improvement": "Home improvement", "new_homes": "New homes", "business": "Business change"}

SUFFIX = (r"Road|Street|Avenue|Lane|Close|Drive|Way|Crescent|Gardens|Grove|Place|Parade|Terrace|Hill|Court|Rise|"
          r"Walk|Square|Broadway|Mews|View|Green|Park|Row|End|Chase|Approach|Meadow|Meadows|Fields|Vale")
ADDR_RE = re.compile(rf"^\s*(?:(?P<door>\d+[A-Za-z]?|[A-Z][\w' ]+?(?:House|Cottage|Lodge|Farm|Barn))\s*,?\s+)?"
                     rf"(?P<street>(?:[A-Z][\w'-]*\s){{1,4}}(?:{SUFFIX}))\b", re.I)


def classify(desc):
    for kind, rx in KINDS:
        if rx.search(desc or ""):
            return None if kind == "skip" else kind
    return None


def parse_address(addr):
    m = ADDR_RE.match(addr or "")
    if not m:
        return None, None
    return (m.group("door") or "").upper() or None, m.group("street").upper().strip()


def parse(records, towns):
    out = []
    for r in records:
        kind = classify(r.get("description"))
        lat, lng = r.get("location_y"), r.get("location_x")
        if not kind or lat is None or lng is None:
            continue
        door, street = parse_address(r.get("address"))
        of = r.get("other_fields") or {}
        out.append({
            "name": r["name"], "address": r.get("address", ""), "description": (r.get("description") or "")[:300],
            "kind": kind, "date": (of.get("date_received") or r.get("start_date") or "")[:10],
            "lat": float(lat), "lng": float(lng), "town": nearest_town(float(lat), float(lng), towns),
            "street": street, "door": door, "link": r.get("link") or of.get("url") or "",
        })
    return out


def fetch(conn, sess, cfg, log):
    conn.execute("CREATE TABLE IF NOT EXISTS planning (name TEXT PRIMARY KEY, address TEXT, description TEXT, kind TEXT, "
                 "date TEXT, lat REAL, lng REAL, town TEXT, street TEXT, door TEXT, link TEXT, fetched_at TEXT)")
    now = datetime.now(timezone.utc).isoformat()
    new = total = 0
    for auth in cfg.get("planning", {}).get("authorities", ["Thurrock"]):
        r = get(sess, API, params={"auth": auth, "recent": cfg.get("planning", {}).get("days", 60), "pg_sz": 500,
                                   "compress": "on"})
        for p in parse(r.json().get("records", []), cfg["towns"]):
            total += 1
            cur = conn.execute("INSERT OR IGNORE INTO planning VALUES (:name,:address,:description,:kind,:date,:lat,:lng,"
                               ":town,:street,:door,:link,:now)", {**p, "now": now})
            new += cur.rowcount
    conn.commit()
    log(f"planning: {total} relevant applications ({new} new)")
    return {"total": total, "new": new}
