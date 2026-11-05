"""Build the mobile web app: static files + today's data.json."""
import json
import shutil
from pathlib import Path

WEB = Path(__file__).parent / "web"


def build(outdir, today, streets, businesses, hotspots, news, crimes, cfg, latest_month, max_streets=600):
    outdir.mkdir(parents=True, exist_ok=True)
    for f in WEB.iterdir():
        shutil.copy(f, outdir / f.name)
    home = cfg["towns"][0]
    data = {
        "generated": today.strftime("%a %d %b"),
        "police_month": latest_month or "n/a",
        "home": {"lat": home["lat"], "lng": home["lng"]},
        "streets": streets[:max_streets],
        "businesses": [{k: b[k] for k in ("key", "name", "btype", "address", "postcode", "lat", "lng",
                                          "score", "new_today", "talking_points")} for b in businesses],
        "hotspots": hotspots,
        "news": news[:40],
        "burglaries": [[round(c["lat"], 5), round(c["lng"], 5)] for c in crimes if c["category"] == "burglary"],
    }
    (outdir / "data.json").write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    return outdir / "index.html"
