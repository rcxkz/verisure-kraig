"""CLI.

  python -m leadfinder run                      fetch everything, score, write today's report
  python -m leadfinder report                   re-score from stored data (no network)
  python -m leadfinder log street "DOCK ROAD|Tilbury" callback --note "wife home after 6"
  python -m leadfinder log business fsa:1234567 appointment
  python -m leadfinder history                  recent logged visits
"""
import argparse
import sys
from datetime import date, datetime, timedelta

from . import config, db, report, scoring, site
from .http import session
from .sources import census, fsa, landreg, landreg_history, news, osm, planning, police

OUTCOMES = ["not_home", "not_interested", "callback", "appointment", "sold", "do_not_return"]
SOURCES = [("Police (data.police.uk)", police), ("News (Google News)", news),
           ("Land Registry sales", landreg), ("Door numbers (10 yrs of sales)", landreg_history),
           ("Planning applications (PlanIt)", planning), ("FSA new food businesses", fsa),
           ("OpenStreetMap businesses", osm)]


def fetch_all(conn, cfg):
    sess = session(cfg["settings"]["user_agent"])
    statuses = {}
    for name, mod in SOURCES:
        msgs = []
        try:
            mod.fetch(conn, sess, cfg, msgs.append)
            statuses[name] = "; ".join(msgs) or "ok"
        except Exception as e:  # one broken source shouldn't kill the report
            statuses[name] = f"FAILED — {type(e).__name__}: {e}"
        print(f"  {name}: {statuses[name]}")
    return statuses


def build(conn, cfg, statuses, online=False):
    today = date.today()
    s = cfg["settings"]
    months = [r["month"] for r in conn.execute("SELECT DISTINCT month FROM crimes ORDER BY month DESC")]
    use = months[: s["crime_months"]]
    latest = use[0] if use else None
    crimes = db.rows(conn, f"SELECT * FROM crimes WHERE month IN ({','.join('?' * len(use))})", use) if use else []
    sales_since = (today - timedelta(days=30 * s["sales_months"])).isoformat()
    sales = db.rows(conn, "SELECT * FROM sales WHERE date >= ?", (sales_since,))
    news_since = (datetime.now() - timedelta(days=s["news_days"])).isoformat()[:10]
    stories = db.rows(conn, "SELECT * FROM news WHERE published >= ? ORDER BY published DESC", (news_since,))
    # only businesses still present in the latest fetch (dropped ones have been inspected / closed)
    # keep each source's businesses only if that source refreshed them in the last week
    biz = db.rows(conn, "SELECT b.* FROM businesses b JOIN (SELECT source, MAX(last_seen) m FROM businesses GROUP BY source) x "
                        "ON b.source = x.source WHERE b.last_seen = x.m AND b.last_seen >= ?",
                  ((today - timedelta(days=7)).isoformat(),))
    visits = db.rows(conn, "SELECT * FROM visits")
    conn.execute("CREATE TABLE IF NOT EXISTS planning (name TEXT PRIMARY KEY, address TEXT, description TEXT, kind TEXT, "
                 "date TEXT, lat REAL, lng REAL, town TEXT, street TEXT, door TEXT, link TEXT, fetched_at TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS doors_known (street TEXT, town TEXT, door TEXT, postcode TEXT, "
                 "PRIMARY KEY (street, town, door))")
    plan_since = (today - timedelta(days=cfg.get("planning", {}).get("days", 60))).isoformat()
    plans = db.rows(conn, "SELECT * FROM planning WHERE date >= ?", (plan_since,))
    known_doors = {}
    for r in conn.execute("SELECT street, town, door FROM doors_known"):
        known_doors.setdefault(f"{r[0]}|{r[1]}", []).append(r[2])

    streets, skipped = scoring.score_streets(crimes, sales, stories, visits, cfg, latest, today, plans)
    try:
        tenure = census.lookup(conn, session(s["user_agent"]), streets, online=online)
        statuses = {**statuses, "Census home ownership": f"{len(tenure)} streets matched"}
    except Exception as e:
        tenure = census.lookup(conn, None, streets, online=False)
        statuses = {**statuses, "Census home ownership": f"FAILED — {type(e).__name__}: {e} (using cache)"}
    streets = scoring.finalize_streets(streets, tenure, known_doors)
    first_run = conn.execute("SELECT COUNT(*) FROM businesses WHERE first_seen < ?",
                             (today.isoformat(),)).fetchone()[0] == 0
    businesses = scoring.score_businesses(biz, crimes, visits, cfg, latest, today, first_run)
    hotspots = scoring.retail_hotspots(crimes)
    statuses = {**statuses, "Hidden (visited recently / excluded)": f"{skipped} streets"}
    path = report.write_all(config.OUTPUT_DIR / today.isoformat(), today, streets, businesses,
                            hotspots, stories, statuses, cfg, latest)
    app = site.build(config.OUTPUT_DIR / "site", today, streets, businesses, hotspots, stories, crimes, cfg, latest)
    print(f"\n{len(streets)} streets, {len(businesses)} businesses, {len(stories)} news stories")
    print(f"Report: {path}")
    print(f"Mobile app: {app}  (serve with: python -m http.server -d output/site 8000)")
    return path


def main(argv=None):
    p = argparse.ArgumentParser(prog="leadfinder")
    p.add_argument("--config")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run")
    sub.add_parser("report")
    lg = sub.add_parser("log")
    lg.add_argument("kind", choices=["street", "business"])
    lg.add_argument("key", help='street: "DOCK ROAD|Tilbury" (shown on the report); business: fsa:123 / osm:node/123')
    lg.add_argument("outcome", choices=OUTCOMES)
    lg.add_argument("--note", default="")
    sub.add_parser("history")
    a = p.parse_args(argv)

    cfg = config.load(a.config)
    conn = db.connect()
    if a.cmd == "run":
        print("Fetching…")
        build(conn, cfg, fetch_all(conn, cfg), online=True)
    elif a.cmd == "report":
        build(conn, cfg, {"note": "re-scored from stored data, no fetch"})
    elif a.cmd == "log":
        conn.execute("INSERT INTO visits (kind, key, outcome, note, ts) VALUES (?,?,?,?,?)",
                     (a.kind, a.key, a.outcome, a.note, datetime.now().isoformat(timespec="seconds")))
        conn.commit()
        print(f"Logged {a.outcome} for {a.key}")
    elif a.cmd == "history":
        for v in db.rows(conn, "SELECT * FROM visits ORDER BY ts DESC LIMIT 50"):
            print(f"{v['ts']}  {v['outcome']:<15} {v['key']}  {v['note']}")


if __name__ == "__main__":
    sys.exit(main())
