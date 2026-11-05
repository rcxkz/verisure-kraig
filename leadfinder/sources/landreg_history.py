"""Real door numbers per street from 10 years of HM Land Registry Price Paid data (OGL).

Every home sold since ~2016 gives us its house number or name. Rebuilt at most every
120 days; each yearly file (~160MB) is streamed and filtered, never stored.
"""
import csv
from datetime import date, datetime, timedelta, timezone

from ..geo import nearest_town
from .landreg import geocode

YEAR_URL = "http://prod2.publicdata.landregistry.gov.uk.s3-website-eu-west-1.amazonaws.com/pp-{year}.csv"
YEARS_BACK = 10
REBUILD_DAYS = 120


def door_label(paon, saon):
    """House number/name. Flats collapse to their building ('FLAT 3' + 'RIVERSIDE HEIGHTS' -> 'RIVERSIDE HEIGHTS')."""
    paon = (paon or "").strip().upper()
    return paon or (saon or "").strip().upper()


def parse_lines(lines, districts):
    districts = {d.upper() for d in districts}
    for row in csv.reader(lines):
        if len(row) < 16 or row[15] == "D":
            continue
        pc = row[3].strip().upper()
        if not pc or pc.split()[0] not in districts:
            continue
        door = door_label(row[7], row[8])
        street = row[9].strip().upper()
        if door and street:
            yield street, door, pc


def fetch(conn, sess, cfg, log):
    conn.execute("CREATE TABLE IF NOT EXISTS doors_known (street TEXT, town TEXT, door TEXT, postcode TEXT, "
                 "PRIMARY KEY (street, town, door))")
    conn.execute("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT)")
    row = conn.execute("SELECT v FROM meta WHERE k='doors_built'").fetchone()
    if row and datetime.fromisoformat(row[0]) > datetime.now(timezone.utc) - timedelta(days=REBUILD_DAYS):
        n = conn.execute("SELECT COUNT(*) FROM doors_known").fetchone()[0]
        log(f"door history: cached ({n} doors)")
        return {"cached": True}

    districts = cfg["landreg"]["postcode_districts"]
    seen = {}
    this_year = date.today().year
    for year in range(this_year - YEARS_BACK, this_year):
        r = sess.get(YEAR_URL.format(year=year), stream=True, timeout=600)
        r.raise_for_status()
        r.encoding = "utf-8"
        for street, door, pc in parse_lines(r.iter_lines(decode_unicode=True), districts):
            seen[(street, door)] = pc
        r.close()
    coords = geocode(conn, sess, list(set(seen.values())))
    conn.execute("DELETE FROM doors_known")
    rows = []
    for (street, door), pc in seen.items():
        lat, lng = coords.get(pc, (None, None))
        if lat is None:
            continue
        rows.append((street, nearest_town(lat, lng, cfg["towns"]), door, pc))
    conn.executemany("INSERT OR IGNORE INTO doors_known VALUES (?,?,?,?)", rows)
    conn.execute("INSERT OR REPLACE INTO meta VALUES ('doors_built', ?)", (datetime.now(timezone.utc).isoformat(),))
    conn.commit()
    log(f"door history: {len(rows)} doors on {len({(r[0], r[1]) for r in rows})} streets from {YEARS_BACK} years of sales")
    return {"doors": len(rows)}
