"""HM Land Registry Price Paid monthly update — recent house sales = new homeowners."""
import csv
import io
import time
from datetime import date, timedelta

from ..config import DATA_DIR
from ..geo import nearest_town
from ..http import get

URL = "http://prod.publicdata.landregistry.gov.uk.s3-website-eu-west-1.amazonaws.com/pp-monthly-update-new-version.csv"
CACHE = DATA_DIR / "cache" / "pp-monthly.csv"
POSTCODES_BULK = "https://api.postcodes.io/postcodes"


def download(sess, max_age_days=7):
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    if CACHE.exists() and time.time() - CACHE.stat().st_mtime < max_age_days * 86400:
        return False
    r = get(sess, URL, timeout=300)
    CACHE.write_bytes(r.content)
    return True


def parse(text, districts, since):
    """Rows: txid, price, date, postcode, type, new, tenure, PAON, SAON, street,
    locality, town, district, county, ppd_cat, record_status."""
    districts = {d.upper() for d in districts}
    out = []
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 16 or row[15] == "D":
            continue
        pc = row[3].strip().upper()
        if not pc or pc.split()[0] not in districts:
            continue
        d = row[2][:10]
        if d < since:
            continue
        out.append({
            "txid": row[0].strip("{}"), "price": int(row[1]), "date": d, "postcode": pc,
            "ptype": row[4], "new_build": row[5], "tenure": row[6], "paon": row[7],
            "saon": row[8], "street": row[9].upper(), "lr_town": row[11],
        })
    return out


def geocode(conn, sess, postcodes):
    known = {r["postcode"] for r in conn.execute("SELECT postcode FROM postcodes")}
    todo = sorted({p for p in postcodes if p not in known})
    for i in range(0, len(todo), 100):
        batch = todo[i:i + 100]
        r = sess.post(POSTCODES_BULK, json={"postcodes": batch}, timeout=60)
        r.raise_for_status()
        for res in r.json()["result"]:
            g = res.get("result")
            conn.execute("INSERT OR REPLACE INTO postcodes VALUES (?,?,?)",
                         (res["query"].upper(), g and g["latitude"], g and g["longitude"]))
    conn.commit()
    return {r["postcode"]: (r["lat"], r["lng"]) for r in conn.execute("SELECT * FROM postcodes")}


def fetch(conn, sess, cfg, log):
    fresh = download(sess)
    since = (date.today() - timedelta(days=30 * cfg["settings"]["sales_months"])).isoformat()
    sales = parse(CACHE.read_text(encoding="utf-8", errors="replace"),
                  cfg["landreg"]["postcode_districts"], since)
    coords = geocode(conn, sess, [s["postcode"] for s in sales])
    stored = 0
    for s in sales:
        lat, lng = coords.get(s["postcode"], (None, None))
        if lat is None:
            continue
        s.update(lat=lat, lng=lng, town=nearest_town(lat, lng, cfg["towns"]))
        cur = conn.execute(
            "INSERT OR IGNORE INTO sales VALUES (:txid,:price,:date,:postcode,:ptype,:new_build,"
            ":tenure,:paon,:saon,:street,:lr_town,:lat,:lng,:town)", s)
        stored += cur.rowcount
    conn.commit()
    log(f"land registry: {'downloaded' if fresh else 'cached'} file, {len(sales)} sales in patch, {stored} new")
    return {"sales": len(sales)}
