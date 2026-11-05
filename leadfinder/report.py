"""Daily report: a single mobile-friendly HTML page plus CSV exports."""
import csv
import html
import json
from urllib.parse import quote_plus

from .scoring import fmt_month

E = html.escape


def maps_link(q):
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(q)}"


def walk_route(leads, start, max_stops=10):
    """Greedy nearest-neighbour ordering of the top streets in the best cluster."""
    from .geo import distance_m
    if not leads:
        return []
    anchor = leads[0]
    pool = [l for l in leads if distance_m(anchor["lat"], anchor["lng"], l["lat"], l["lng"]) < 1500]
    route, cur = [], (anchor["lat"], anchor["lng"])
    pool = pool[:max_stops * 2]
    while pool and len(route) < max_stops:
        nxt = min(pool, key=lambda l: distance_m(cur[0], cur[1], l["lat"], l["lng"]))
        route.append(nxt)
        pool.remove(nxt)
        cur = (nxt["lat"], nxt["lng"])
    return route


def directions_link(route):
    if not route:
        return ""
    pts = [f"{r['lat']},{r['lng']}" for r in route]
    url = ("https://www.google.com/maps/dir/?api=1&travelmode=walking"
           f"&origin={pts[0]}&destination={pts[-1]}")
    if len(pts) > 2:
        url += "&waypoints=" + quote_plus("|".join(pts[1:-1][:8]))
    return url


CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#1a1d23;--muted:#5f6670;--line:#e3e6ea;--accent:#c8102e;--chip:#f1f3f5}
@media (prefers-color-scheme:dark){:root{--bg:#121417;--card:#1b1e23;--ink:#eceef1;--muted:#9aa1ab;--line:#2b3037;--accent:#ff4d5e;--chip:#252a31}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:860px;margin:0 auto;padding:16px}
h1{font-size:22px;margin:4px 0}h2{font-size:17px;margin:28px 0 10px;padding-bottom:6px;border-bottom:2px solid var(--accent)}
.sub{color:var(--muted);font-size:13px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:10px 0}
.row{display:flex;justify-content:space-between;gap:10px;align-items:baseline}
.t{font-weight:600}.score{font-variant-numeric:tabular-nums;font-weight:700;color:var(--accent);white-space:nowrap}
ul{margin:6px 0 0;padding-left:18px}li{margin:2px 0}
a{color:inherit}a.btn{display:inline-block;margin-top:8px;padding:6px 10px;border:1px solid var(--line);border-radius:6px;text-decoration:none;font-size:13px;background:var(--chip)}
.chip{display:inline-block;font-size:11px;padding:1px 7px;border-radius:99px;background:var(--chip);color:var(--muted);margin-left:6px}
.new{background:var(--accent);color:#fff}
table{width:100%;border-collapse:collapse;font-size:14px}td,th{text-align:left;padding:6px 4px;border-bottom:1px solid var(--line)}
th{color:var(--muted);font-weight:500;font-size:12px}
.rules{font-size:13px;color:var(--muted)}
details summary{cursor:pointer;color:var(--muted);font-size:13px}
"""


def render(today, streets, businesses, hotspots, news, statuses, cfg, latest_month):
    route = walk_route(streets[:200], cfg["towns"][0])
    out = [f"<!doctype html><html lang=en><head><meta charset=utf-8>"
           f"<meta name=viewport content='width=device-width,initial-scale=1'>"
           f"<title>Leads {today}</title><style>{CSS}</style></head><body><main>"]
    out.append(f"<h1>Daily leads — {today:%a %d %b %Y}</h1>")
    out.append(f"<div class=sub>Police data up to {fmt_month(latest_month) if latest_month else 'n/a'} · "
               f"{len(streets)} streets · {len(businesses)} businesses</div>")

    if route:
        out.append("<h2>Today's walking route</h2><div class=card><ol>")
        for r in route:
            out.append(f"<li><b>{E(r['street'])}</b>, {E(r['town'])} <span class=chip>{r['score']}</span></li>")
        out.append(f"</ol><a class=btn href='{E(directions_link(route))}'>Open walking route in Google Maps</a></div>")

    out.append("<h2>Top streets to door-knock</h2>")
    for s in streets[: cfg["settings"]["top_streets"]]:
        out.append(f"<div class=card><div class=row><div class=t>{E(s['street'])}, {E(s['town'])}</div>"
                   f"<div class=score>{s['score']}</div></div><ul>")
        out += [f"<li>{E(p)}</li>" for p in s["talking_points"]]
        out.append(f"</ul><a class=btn href='{E(maps_link(s['street'] + ', ' + s['town']))}'>Map</a>"
                   f" <span class=sub>log: <code>python -m leadfinder log street \"{E(s['key'])}\" not_home</code></span></div>")

    out.append("<h2>Businesses to visit or call</h2>")
    for b in businesses[: cfg["settings"]["top_businesses"]]:
        badge = "<span class='chip new'>NEW TODAY</span>" if b["new_today"] else ""
        out.append(f"<div class=card><div class=row><div class=t>{E(b['name'])}{badge}"
                   f"<span class=chip>{E(b['btype'])}</span></div><div class=score>{b['score']}</div></div>"
                   f"<div class=sub>{E(b['address'])} {E(b['postcode'] or '')}</div><ul>")
        out += [f"<li>{E(p)}</li>" for p in b["talking_points"]]
        out.append(f"</ul><a class=btn href='{E(maps_link(b['name'] + ' ' + (b['postcode'] or b['address'])))}'>"
                   f"Find on Maps (phone number, hours)</a></div>")

    if hotspots:
        out.append("<h2>Shop strips with most theft</h2><div class=card><table><tr><th>Street</th><th>Town</th>"
                   "<th>Shoplifting</th><th>Robbery</th></tr>")
        for h in hotspots:
            out.append(f"<tr><td><a href='{E(maps_link(h['street'] + ', ' + h['town']))}'>{E(h['street'])}</a></td>"
                       f"<td>{E(h['town'])}</td><td>{h['shoplifting']}</td><td>{h['robbery']}</td></tr>")
        out.append("</table></div>")

    out.append("<h2>Local crime news</h2>")
    if not news:
        out.append("<div class=card sub>No matching stories in the window.</div>")
    for n in news[:30]:
        out.append(f"<div class=card><a href='{E(n['link'])}'><b>{E(n['title'])}</b></a>"
                   f"<div class=sub>{E(n['source'])} · {E(n['town'])} · {E(n['published'][:10])}</div></div>")

    out.append("<h2>Ground rules</h2><div class='card rules'><ul>"
               "<li>Talk about the <b>area</b>, never a named victim or a specific house that was burgled.</li>"
               "<li>Police locations are approximate (“on or near”) — quote them that way.</li>"
               "<li>Respect No Cold Calling Zones and “no cold callers” stickers. Add zones to config.toml.</li>"
               "<li>Before phoning a business, check the number against the CTPS; individuals against the TPS.</li>"
               "<li>Doorstep sales carry a 14-day cancellation right — say so.</li></ul></div>")

    out.append("<details><summary>Data sources run</summary><ul class=rules>")
    out += [f"<li>{E(k)}: {E(v)}</li>" for k, v in statuses.items()]
    out.append("</ul></details></main></body></html>")
    return "\n".join(out)


def write_csv(path, rows, fields):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: (" | ".join(v) if isinstance(v, list) else v) for k, v in r.items()})


def write_all(outdir, today, streets, businesses, hotspots, news, statuses, cfg, latest_month):
    outdir.mkdir(parents=True, exist_ok=True)
    page = render(today, streets, businesses, hotspots, news, statuses, cfg, latest_month)
    (outdir / "report.html").write_text(page, encoding="utf-8")
    write_csv(outdir / "streets.csv", streets,
              ["score", "street", "town", "burglaries", "nearby_burglaries", "vehicle_crimes", "robberies",
               "recent_sales", "sale_doors", "news", "talking_points", "lat", "lng", "key"])
    write_csv(outdir / "businesses.csv", businesses,
              ["score", "name", "btype", "address", "postcode", "signal", "new_today", "talking_points", "key"])
    (outdir / "leads.json").write_text(json.dumps({"streets": streets, "businesses": businesses}, indent=1))
    return outdir / "report.html"
