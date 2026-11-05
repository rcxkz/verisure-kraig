from datetime import date

from leadfinder.geo import normalize_street
from leadfinder.scoring import recency, score_businesses, score_streets
from leadfinder.sources import news, police

CFG = {
    "settings": {"nearby_metres": 500, "revisit_cooldown_days": 21, "news_days": 14},
    "exclusions": {"streets": ["Quiet Lane, Tilbury"], "postcode_prefixes": []},
    "towns": [{"name": "Tilbury", "lat": 51.4625, "lng": 0.3586}],
}
TODAY = date(2026, 11, 5)


def crime(i, street, cat="burglary", month="2026-08", lat=51.4625, lng=0.3586):
    return {"id": i, "category": cat, "month": month, "lat": lat, "lng": lng,
            "street": f"On or near {street}", "town": "Tilbury", "outcome": None}


def test_normalize_street():
    assert normalize_street("On or near Dock Road") == "DOCK ROAD"


def test_recency_decays():
    assert recency("2026-08", "2026-08") == 1.0
    assert recency("2026-06", "2026-08") == 0.5


def test_burgled_street_ranks_above_quiet_one():
    crimes = [crime(1, "Dock Road"), crime(2, "Dock Road"),
              crime(3, "Far Road", cat="other-theft", lat=51.50, lng=0.40)]
    leads, _ = score_streets(crimes, [], [], [], CFG, "2026-08", TODAY)
    assert leads[0]["street"] == "Dock Road"
    assert leads[0]["burglaries"] == 2
    assert "2 burglaries" in leads[0]["talking_points"][0]


def test_nearby_burglary_counted_for_neighbour():
    crimes = [crime(1, "Dock Road"), crime(2, "Calcutta Road", cat="vehicle-crime", lng=0.3600)]
    leads, _ = score_streets(crimes, [], [], [], CFG, "2026-08", TODAY)
    calc = next(l for l in leads if l["street"] == "Calcutta Road")
    assert calc["nearby_burglaries"] == 1


def test_recent_visit_and_exclusion_hide_street():
    crimes = [crime(1, "Dock Road"), crime(2, "Quiet Lane")]
    visits = [{"kind": "street", "key": "DOCK ROAD|Tilbury", "outcome": "not_home", "ts": "2026-11-01T10:00:00"}]
    leads, skipped = score_streets(crimes, [], [], visits, CFG, "2026-08", TODAY)
    assert leads == [] and skipped == 2


def test_sales_add_new_owner_point():
    sale = {"street": "DOCK ROAD", "town": "Tilbury", "lat": 51.4625, "lng": 0.3586,
            "postcode": "RM18 7AA", "saon": "", "paon": "12"}
    leads, _ = score_streets([], [sale], [], [], CFG, "2026-08", TODAY)
    assert "No. 12" in leads[0]["talking_points"][0]


def test_business_crime_bonus_is_capped():
    b = {"source": "fsa", "ext_id": "1", "name": "Shop", "btype": "Retailers - other", "address": "",
         "postcode": "", "lat": 51.4625, "lng": 0.3586, "signal": "new", "first_seen": "2026-11-05"}
    crimes = [crime(i, "Mall", cat="shoplifting") for i in range(200)]
    [lead] = score_businesses([b], crimes, [], CFG, "2026-08", TODAY, first_run=True)
    assert lead["score"] == 3 + 6.0 and not lead["new_today"]


def test_police_parse_strings_and_filter():
    raw = [{"category": "burglary", "id": 9, "month": "2026-08", "outcome_status": None,
            "location": {"latitude": "51.4596", "longitude": "0.3616", "street": {"name": "On or near Auckland Close"}}},
           {"category": "drugs", "id": 10, "month": "2026-08", "location": {}}]
    out = police.parse(raw, CFG["towns"])
    assert len(out) == 1 and out[0]["lat"] == 51.4596 and out[0]["town"] == "Tilbury"


def test_news_parse_filters_to_patch():
    from datetime import datetime, timezone
    xml = """<rss><channel>
    <item><title>Burglars target homes in Grays - Thurrock Gazette</title><link>a</link>
      <pubDate>Tue, 03 Nov 2026 09:00:00 GMT</pubDate><source>Thurrock Gazette</source></item>
    <item><title>Fareham burglary appeal - Portsmouth News</title><link>b</link>
      <pubDate>Tue, 03 Nov 2026 09:00:00 GMT</pubDate><source>Portsmouth News</source></item>
    </channel></rss>"""
    out = news.parse(xml, ["Grays"], datetime(2026, 10, 1, tzinfo=timezone.utc))
    assert [s["link"] for s in out] == ["a"] and out[0]["town"] == "Grays"
