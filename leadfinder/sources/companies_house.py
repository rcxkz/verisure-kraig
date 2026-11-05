"""Companies House advanced search — newly incorporated shops/salons/cafés. Needs a free API key."""
import os
from datetime import date, timedelta

from ..http import get
from .fsa import upsert

URL = "https://api.company-information.service.gov.uk/advanced-search/companies"

SIC_LABELS = {"47": "Retail", "56": "Food & drink", "55": "Hotel / B&B", "45": "Motor trade",
              "9602": "Hair & beauty", "9604": "Gym / wellbeing", "75": "Vet", "8623": "Dentist"}


def label(sics, prefixes):
    for s in sics:
        for p in prefixes:
            if s.startswith(p):
                return SIC_LABELS.get(p, f"SIC {s}")
    return None


def parse(items, prefixes, today):
    out = []
    for c in items:
        kind = label(c.get("sic_codes") or [], prefixes)
        if not kind:
            continue
        a = c.get("registered_office_address") or {}
        out.append({
            "source": "companies_house", "ext_id": c["company_number"], "name": c.get("company_name", ""),
            "btype": kind,
            "address": ", ".join(x for x in (a.get("address_line_1"), a.get("address_line_2"), a.get("locality")) if x),
            "postcode": (a.get("postal_code") or "").upper(), "lat": None, "lng": None,
            "signal": f"New company incorporated {c.get('date_of_creation', '')} (registered office — may be an accountant's address)",
            "signal_date": c.get("date_of_creation"), "today": today,
        })
    return out


def fetch(conn, sess, cfg, log):
    key = os.environ.get("COMPANIES_HOUSE_API_KEY")
    if not key:
        log("companies house: skipped (set COMPANIES_HOUSE_API_KEY to enable)")
        return {"skipped": True}
    ch = cfg["companies_house"]
    since = (date.today() - timedelta(days=ch["lookback_days"])).isoformat()
    today = date.today().isoformat()
    total = new = 0
    for t in cfg["towns"]:
        r = get(sess, URL, auth=(key, ""), params={
            "location": t["name"], "incorporated_from": since, "company_status": "active", "size": 500})
        for b in parse(r.json().get("items", []), ch["sic_prefixes"], today):
            total += 1
            new += upsert(conn, b)
    conn.commit()
    log(f"companies house: {total} relevant new companies ({new} first seen today)")
    return {"total": total, "new": new}
