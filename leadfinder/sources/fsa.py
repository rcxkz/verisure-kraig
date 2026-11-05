"""Food Standards Agency ratings — 'AwaitingInspection' = newly registered food business."""
from datetime import date

from ..http import get

BASE = "https://api.ratings.food.gov.uk"
HDR = {"x-api-version": "2", "Accept": "application/json"}

SKIP_TYPES = {"Mobile caterer", "School/college/university", "Caring Premises",
              "Distributors/Transporters", "Importers/Exporters", "Farmers/growers"}


def _addr(e):
    return ", ".join(x for x in (e.get(f"AddressLine{i}") for i in range(1, 5)) if x)


def parse(establishments, today):
    out = []
    for e in establishments:
        if e.get("RatingValue") != "AwaitingInspection" or e.get("BusinessType") in SKIP_TYPES:
            continue
        g = e.get("geocode") or {}
        try:
            lat, lng = float(g["latitude"]), float(g["longitude"])
        except (KeyError, TypeError, ValueError):
            lat = lng = None
        out.append({
            "source": "fsa", "ext_id": str(e["FHRSID"]), "name": e.get("BusinessName", ""),
            "btype": e.get("BusinessType", ""), "address": _addr(e), "postcode": e.get("PostCode", ""),
            "lat": lat, "lng": lng, "signal": "New food business (awaiting first inspection)",
            "signal_date": None, "today": today, "phone": (e.get("Phone") or "").strip(),
        })
    return out


def fetch(conn, sess, cfg, log):
    auths = get(sess, f"{BASE}/Authorities/basic", headers=HDR).json()["authorities"]
    wanted = {c.lower() for c in cfg["fsa"]["councils"]}
    ids = [a["LocalAuthorityId"] for a in auths if a["Name"].lower() in wanted]
    today = date.today().isoformat()
    total = new = 0
    for la in ids:
        page = 1
        while True:
            d = get(sess, f"{BASE}/Establishments", headers=HDR,
                    params={"localAuthorityId": la, "pageSize": 5000, "pageNumber": page}).json()
            for b in parse(d["establishments"], today):
                total += 1
                new += upsert(conn, b)
            if page >= d["meta"]["totalPages"]:
                break
            page += 1
    conn.commit()
    log(f"fsa: {total} new food businesses across {len(ids)} councils ({new} first seen today)")
    return {"total": total, "new": new}


def upsert(conn, b):
    """Insert or refresh a business; returns 1 if never seen before."""
    b = {"phone": "", "chain": 0, **b}
    cur = conn.execute(
        "INSERT OR IGNORE INTO businesses (source, ext_id, name, btype, address, postcode, lat, lng, signal, "
        "signal_date, first_seen, last_seen, phone, chain) VALUES (:source,:ext_id,:name,:btype,:address,:postcode,"
        ":lat,:lng,:signal,:signal_date,:today,:today,:phone,:chain)", b)
    if cur.rowcount == 0:
        conn.execute("UPDATE businesses SET last_seen=:today, signal=:signal, phone=COALESCE(NULLIF(:phone,''), phone), "
                     "btype=:btype, name=:name WHERE source=:source AND ext_id=:ext_id", b)
    return cur.rowcount
