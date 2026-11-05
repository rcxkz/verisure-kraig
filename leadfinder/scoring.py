"""Turn raw data into ranked street and business leads with talking points.

Pure functions — no network or database — so they're easy to test and tune.
"""
from collections import defaultdict
from datetime import datetime

from .geo import distance_m, is_door_street, normalize_street, pretty_street

# --- tuning knobs -----------------------------------------------------------
W_OWN_BURGLARY = 4.0      # burglary recorded on/near this street
W_NEARBY_BURGLARY = 1.0   # burglary within nearby_metres
W_VEHICLE = 1.5
W_ROBBERY = 1.0
W_DAMAGE = 0.5
W_SALE = 2.5              # each recent house sale (new owner), capped
SALE_CAP = 5
W_STREET_NEWS = 6.0       # news story naming this street
W_TOWN_NEWS = 0.5         # each story in the town, capped
TOWN_NEWS_CAP = 4

BUSINESS_TYPE_WEIGHT = {
    "Retailers - other": 3, "Pub/bar/nightclub": 3, "Takeaway/sandwich shop": 2,
    "Restaurant/Cafe/Canteen": 2, "Retailers - supermarkets/hypermarkets": 2,
    "Hotel/bed & breakfast/guest house": 2, "Other catering premises": 1,
    "Manufacturers/packers": 1,
    "Retail": 3, "Food & drink": 2, "Motor trade": 3, "Hair & beauty": 2, "Vet": 2,
    "Dentist": 2, "Gym / wellbeing": 1, "Hotel / B&B": 2,
}
BUSINESS_CRIMES = {"burglary": 2.0, "robbery": 2.0, "shoplifting": 1.0, "criminal-damage-arson": 1.0}
W_NEW_TODAY = 3.0
BUSINESS_CRIME_CAP = 6.0   # stop shopping-centre units swamping the list

MONTH_NAMES = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def month_diff(a, b):
    ya, ma = map(int, a.split("-"))
    yb, mb = map(int, b.split("-"))
    return (ya - yb) * 12 + (ma - mb)


def recency(month, latest):
    return max(0.25, 1.0 - 0.25 * month_diff(latest, month))


def fmt_month(m):
    y, mo = m.split("-")
    return f"{MONTH_NAMES[int(mo) - 1]} {y}"


def street_key(street, town):
    return f"{street}|{town}"


def _excluded(street, town, postcodes, excl):
    label = f"{pretty_street(street)}, {town}".lower()
    if any(label == e.lower() for e in excl.get("streets", [])):
        return True
    return any(pc.startswith(p.upper()) for pc in postcodes for p in excl.get("postcode_prefixes", []))


def _blocked_keys(visits, today, cooldown_days):
    blocked = set()
    for v in visits:
        if v["outcome"] in ("do_not_return", "sold"):
            blocked.add(v["key"])
            continue
        age = (today - datetime.fromisoformat(v["ts"]).date()).days
        if age < cooldown_days:
            blocked.add(v["key"])
    return blocked


def score_streets(crimes, sales, news, visits, cfg, latest_month, today):
    s = cfg["settings"]
    near_m = s["nearby_metres"]
    streets = defaultdict(lambda: {"crimes": [], "sales": [], "news": [], "pts": []})

    for c in crimes:
        st = normalize_street(c["street"])
        if not is_door_street(st):
            continue
        d = streets[street_key(st, c["town"])]
        d["crimes"].append(c)
        d["pts"].append((c["lat"], c["lng"]))
    for x in sales:
        if not x["street"]:
            continue
        d = streets[street_key(x["street"], x["town"])]
        d["sales"].append(x)
        d["pts"].append((x["lat"], x["lng"]))

    town_news = defaultdict(list)
    for n in news:
        town_news[n["town"]].append(n)
        if n.get("street"):
            k = street_key(n["street"], n["town"])
            if k in streets:
                streets[k]["news"].append(n)

    burglaries = [c for c in crimes if c["category"] == "burglary"]
    blocked = _blocked_keys([v for v in visits if v["kind"] == "street"], today, s["revisit_cooldown_days"])
    months = sorted({c["month"] for c in crimes})
    period = f"{fmt_month(months[0])}–{fmt_month(months[-1])}" if months else ""

    leads, skipped = [], 0
    for key, d in streets.items():
        street, town = key.split("|", 1)
        if key in blocked or _excluded(street, town, [x["postcode"] for x in d["sales"]], cfg["exclusions"]):
            skipped += 1
            continue
        lat = sum(p[0] for p in d["pts"]) / len(d["pts"])
        lng = sum(p[1] for p in d["pts"]) / len(d["pts"])

        by_cat = defaultdict(float)
        counts = defaultdict(int)
        own_ids = set()
        for c in d["crimes"]:
            by_cat[c["category"]] += recency(c["month"], latest_month)
            counts[c["category"]] += 1
            own_ids.add(c["id"])
        nearby = [b for b in burglaries if b["id"] not in own_ids
                  and distance_m(lat, lng, b["lat"], b["lng"]) <= near_m]
        nearby_w = sum(recency(b["month"], latest_month) for b in nearby)
        tn = town_news.get(town, [])

        score = (W_OWN_BURGLARY * by_cat["burglary"] + W_NEARBY_BURGLARY * nearby_w
                 + W_VEHICLE * by_cat["vehicle-crime"] + W_ROBBERY * by_cat["robbery"]
                 + W_DAMAGE * by_cat["criminal-damage-arson"]
                 + W_SALE * min(len(d["sales"]), SALE_CAP)
                 + W_STREET_NEWS * len(d["news"]) + W_TOWN_NEWS * min(len(tn), TOWN_NEWS_CAP))
        if score <= 0:
            continue

        pts = []
        if counts["burglary"]:
            pts.append(f"{counts['burglary']} burglar{'y' if counts['burglary'] == 1 else 'ies'} "
                       f"reported on or near this street ({period}, police.uk)")
        if nearby:
            pts.append(f"{len(nearby)} more burglar{'y' if len(nearby) == 1 else 'ies'} within a 5-minute walk")
        if counts["vehicle-crime"]:
            pts.append(f"{counts['vehicle-crime']} vehicle crime{'s' if counts['vehicle-crime'] > 1 else ''} "
                       "on or near this street — outdoor camera / driveway angle")
        if counts["robbery"]:
            pts.append(f"{counts['robbery']} robbery report{'s' if counts['robbery'] > 1 else ''} on or near this street")
        if d["sales"]:
            doors = sorted({" ".join(x for x in (sl["saon"], sl["paon"]) if x) for sl in d["sales"]})
            pts.append(f"{len(d['sales'])} home{'s' if len(d['sales']) > 1 else ''} sold recently — new owners "
                       f"(No. {', '.join(doors[:8])})")
        for n in d["news"][:2]:
            pts.append(f"In the news: \"{n['title']}\" ({n['source']})")
        if not d["news"] and tn:
            pts.append(f"{len(tn)} local crime stor{'y' if len(tn) == 1 else 'ies'} in {town} in the last "
                       f"{s['news_days']} days")

        leads.append({
            "key": key, "street": pretty_street(street), "town": town, "score": round(score, 1),
            "lat": round(lat, 5), "lng": round(lng, 5),
            "burglaries": counts["burglary"], "nearby_burglaries": len(nearby),
            "vehicle_crimes": counts["vehicle-crime"], "robberies": counts["robbery"],
            "recent_sales": len(d["sales"]), "news": len(d["news"]),
            "sale_doors": sorted({" ".join(x for x in (sl["saon"], sl["paon"]) if x) for sl in d["sales"]}),
            "talking_points": pts,
        })
    leads.sort(key=lambda x: -x["score"])
    return leads, skipped


def score_businesses(businesses, crimes, visits, cfg, latest_month, today, first_run=False):
    blocked = _blocked_keys([v for v in visits if v["kind"] == "business"], today,
                            cfg["settings"]["revisit_cooldown_days"])
    biz_crimes = [c for c in crimes if c["category"] in BUSINESS_CRIMES]
    leads = []
    for b in businesses:
        key = f"{b['source']}:{b['ext_id']}"
        if key in blocked:
            continue
        score = BUSINESS_TYPE_WEIGHT.get(b["btype"], 1)
        pts = [b["signal"]]
        near = defaultdict(int)
        crime_pts = 0.0
        if b["lat"] is not None:
            for c in biz_crimes:
                if distance_m(b["lat"], b["lng"], c["lat"], c["lng"]) <= 300:
                    near[c["category"]] += 1
                    crime_pts += BUSINESS_CRIMES[c["category"]] * recency(c["month"], latest_month) * 0.5
        score += min(crime_pts, BUSINESS_CRIME_CAP)
        if near:
            pts.append("Within 300m: " + ", ".join(f"{v} {k.replace('-', ' ')}" for k, v in sorted(near.items())))
        new_today = not first_run and b["first_seen"] == today.isoformat()
        if new_today:
            score += W_NEW_TODAY
        leads.append({**b, "key": key, "score": round(score, 1), "new_today": new_today,
                      "nearby": dict(near), "talking_points": pts})
    leads.sort(key=lambda x: -x["score"])
    return leads


def retail_hotspots(crimes, limit=15):
    """Streets with the most shoplifting/robbery — shop strips worth walking for business visits."""
    agg = defaultdict(lambda: defaultdict(int))
    for c in crimes:
        if c["category"] in ("shoplifting", "robbery"):
            st = normalize_street(c["street"])
            if is_door_street(st):
                agg[(st, c["town"])][c["category"]] += 1
    out = [{"street": pretty_street(st), "town": t, "shoplifting": v["shoplifting"], "robbery": v["robbery"]}
           for (st, t), v in agg.items()]
    out.sort(key=lambda x: -(x["shoplifting"] + 2 * x["robbery"]))
    return out[:limit]
