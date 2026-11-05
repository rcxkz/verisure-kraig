"""data.police.uk — street-level crime, monthly, ~2 month publication lag."""
from datetime import datetime, timezone

from ..geo import nearest_town
from ..http import get

BASE = "https://data.police.uk/api"

# Categories that matter for a security sale
CATEGORIES = {
    "burglary",
    "robbery",
    "vehicle-crime",
    "shoplifting",
    "criminal-damage-arson",
    "theft-from-the-person",
    "other-theft",
    "bicycle-theft",
}


def latest_months(sess, n):
    data = get(sess, f"{BASE}/crimes-street-dates").json()
    return sorted({d["date"] for d in data}, reverse=True)[:n]


def parse(items, towns):
    out = []
    for c in items:
        if c.get("category") not in CATEGORIES:
            continue
        loc = c.get("location") or {}
        try:
            lat, lng = float(loc["latitude"]), float(loc["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        out.append({
            "id": c["id"],
            "category": c["category"],
            "month": c["month"],
            "lat": lat,
            "lng": lng,
            "street": (loc.get("street") or {}).get("name", ""),
            "town": nearest_town(lat, lng, towns),
            "outcome": (c.get("outcome_status") or {}).get("category"),
        })
    return out


def fetch(conn, sess, cfg, log):
    towns = cfg["towns"]
    months = latest_months(sess, cfg["settings"]["crime_months"])
    done = {(r["town"], r["month"]) for r in conn.execute("SELECT town, month FROM crime_fetches")}
    new = 0
    for month in months:
        for t in towns:
            if (t["name"], month) in done:
                continue
            r = get(sess, f"{BASE}/crimes-street/all-crime",
                    params={"lat": t["lat"], "lng": t["lng"], "date": month})
            crimes = parse(r.json(), towns)
            conn.executemany(
                "INSERT OR IGNORE INTO crimes VALUES (:id,:category,:month,:lat,:lng,:street,:town,:outcome)",
                crimes)
            conn.execute("INSERT OR REPLACE INTO crime_fetches VALUES (?,?,?)",
                         (t["name"], month, datetime.now(timezone.utc).isoformat()))
            conn.commit()
            new += len(crimes)
    log(f"police: months {', '.join(months)} — {new} new relevant crimes stored")
    return {"months": months, "latest": months[0] if months else None}
