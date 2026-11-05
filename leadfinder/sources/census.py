"""Census 2021 tenure (TS054) per output area (~125 households) via Nomis.

Owner-occupiers can sign up for an alarm; most tenants can't. Each street is matched to the
output area at its centre using postcodes.io. Census data never changes, so it's cached for good.
"""
from ..http import get

NOMIS = "https://www.nomisweb.co.uk/api/v01/dataset/NM_2072_1.data.csv"
REVERSE = "https://api.postcodes.io/postcodes"


def _tables(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS street_oa (key TEXT PRIMARY KEY, oa TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS oa_tenure (oa TEXT PRIMARY KEY, households INTEGER, owned INTEGER, "
                 "social INTEGER, private INTEGER)")


def parse_nomis(csv_text):
    import csv
    import io
    out = {}
    for row in csv.DictReader(io.StringIO(csv_text)):
        oa, name, v = row["GEOGRAPHY_CODE"], row["C2021_TENURE_9_NAME"], int(row["OBS_VALUE"])
        d = out.setdefault(oa, {"households": 0, "owned": 0, "social": 0, "private": 0})
        if name == "Total: All households":
            d["households"] = v
        elif name in ("Owned", "Shared ownership"):
            d["owned"] += v
        elif name == "Social rented":
            d["social"] = v
        elif name == "Private rented":
            d["private"] = v
    return out


def lookup(conn, sess, leads, online=True):
    """Returns {street_key: owner_share 0..1}. Uses cache; fills gaps when online."""
    _tables(conn)
    known = {r[0]: r[1] for r in conn.execute("SELECT key, oa FROM street_oa")}
    if online:
        todo = [l for l in leads if l["key"] not in known]
        for i in range(0, len(todo), 100):
            batch = todo[i:i + 100]
            r = sess.post(REVERSE, json={"geolocations": [
                {"longitude": l["lng"], "latitude": l["lat"], "radius": 300, "limit": 1} for l in batch]}, timeout=60)
            r.raise_for_status()
            for l, res in zip(batch, r.json()["result"]):
                hits = res.get("result") or []
                oa = hits[0]["codes"].get("oa21") if hits else None
                known[l["key"]] = oa
                conn.execute("INSERT OR REPLACE INTO street_oa VALUES (?,?)", (l["key"], oa))
        have = {r[0] for r in conn.execute("SELECT oa FROM oa_tenure")}
        need = sorted({oa for oa in known.values() if oa and oa not in have})
        for i in range(0, len(need), 80):
            r = get(sess, NOMIS, params={"date": "latest", "geography": ",".join(need[i:i + 80]), "measures": 20100,
                                         "select": "geography_code,c2021_tenure_9_name,obs_value"})
            for oa, d in parse_nomis(r.text).items():
                conn.execute("INSERT OR REPLACE INTO oa_tenure VALUES (?,?,?,?,?)",
                             (oa, d["households"], d["owned"], d["social"], d["private"]))
        conn.commit()
    ten = {r[0]: r for r in conn.execute("SELECT oa, households, owned FROM oa_tenure")}
    out = {}
    for key, oa in known.items():
        t = ten.get(oa)
        if t and t[1]:
            out[key] = t[2] / t[1]
    return out
