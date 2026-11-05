"""Local crime news via Google News RSS."""
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from ..http import get

RSS = "https://news.google.com/rss/search"
KEYWORDS = ("burgl", "break-in", "broke into", "breaking into", "raid", "robb", "theft",
            "stolen", "steal", "thief", "thieves", "smash", "intruder", "raider", "looted",
            "shoplift", "arson", "break in")
STREET_RE = re.compile(
    r"\b((?:[A-Z][a-z']+\s){1,3}(?:Road|Street|Avenue|Lane|Close|Drive|Way|Crescent|Gardens|"
    r"Grove|Place|Parade|Terrace|Hill|Court|Rise|Walk|Square|Broadway))\b")

# Council/area names that cover several towns — stories about these are kept as area news
AREAS = ("South Essex", "Thurrock", "Basildon", "Brentwood", "Castle Point", "Havering", "Southend")

# Local papers whose crime stories are kept even if the headline names no town
LOCAL_SOURCES = ("Southend Echo", "Thurrock Gazette", "Yellow Advertiser", "Thurrock Independent",
                 "Brentwood Gazette", "Romford Recorder", "Basildon Canvey Southend Echo", "Essex Police")


def _query(town, days):
    kw = '(burglary OR burglars OR "break-in" OR "ram raid" OR robbery OR "shop theft" OR raiders)'
    return f'{kw} "{town}" when:{days}d'


def parse(xml_text, place_names, cutoff):
    """Returns story dicts. Only keeps crime stories whose title names one of our places."""
    root = ET.fromstring(xml_text)
    out = []
    for it in root.iter("item"):
        title = it.findtext("title") or ""
        source = it.findtext("source") or ""
        if source and title.endswith(" - " + source):
            title = title[: -len(source) - 3]
        low = title.lower()
        if not any(k in low for k in KEYWORDS):
            continue
        place = next((p for p in place_names if re.search(rf"\b{re.escape(p.lower())}\b", low)), None)
        if not place and source in LOCAL_SOURCES:
            place = "South Essex"
        if not place:
            continue
        try:
            pub = parsedate_to_datetime(it.findtext("pubDate"))
        except (TypeError, ValueError):
            continue
        if pub < cutoff:
            continue
        m = STREET_RE.search(title)
        out.append({
            "link": it.findtext("link"),
            "title": title,
            "source": source,
            "published": pub.isoformat(),
            "town": place,
            "street": m.group(1).upper() if m else None,
        })
    return out


def fetch(conn, sess, cfg, log):
    days = cfg["settings"]["news_days"]
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    # longest names first so "Chadwell St Mary" beats "Grays" etc.
    places = sorted([t["name"] for t in cfg["towns"]] + list(AREAS), key=len, reverse=True)
    now = datetime.now(timezone.utc).isoformat()
    seen = 0
    for name in [t["name"] for t in cfg["towns"]] + list(AREAS):
        r = get(sess, RSS, params={"q": _query(name, days), "hl": "en-GB", "gl": "GB", "ceid": "GB:en"})
        for s in parse(r.text, places, cutoff):
            cur = conn.execute(
                "INSERT OR IGNORE INTO news VALUES (:link,:title,:source,:published,:town,:street,:fetched)",
                {**s, "fetched": now})
            seen += cur.rowcount
    conn.commit()
    log(f"news: {seen} new local crime stories")
    return {"new": seen}
