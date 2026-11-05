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
    assert lead["score"] == 3 + 6.0 + 3.0 and not lead["new_today"]  # type + capped crime + new-business bonus


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


# --- new sources -----------------------------------------------------------
from leadfinder.scoring import finalize_streets
from leadfinder.sources import census, landreg_history, osm, planning


def test_planning_classify_and_address():
    assert planning.classify("Single storey rear extension") == "home_improvement"
    assert planning.classify("Erection of 12 dwellings with parking") == "new_homes"
    assert planning.classify("Change of use from office to hot food takeaway") == "business"
    assert planning.classify("T1 Oak - fell") is None
    assert planning.parse_address("72 Gilbert Road Chafford Hundred Grays Essex RM16 6NR") == ("72", "GILBERT ROAD")
    assert planning.parse_address("Rose Cottage, Stock Road, Billericay") == ("ROSE COTTAGE", "STOCK ROAD")


def test_census_parse_owner_share():
    csv_text = ('"GEOGRAPHY_CODE","C2021_TENURE_9_NAME","OBS_VALUE"\n"E1","Total: All households",100\n'
                '"E1","Owned",60\n"E1","Owned: Owns outright",30\n"E1","Shared ownership",2\n"E1","Social rented",20\n'
                '"E1","Private rented",18\n')
    assert census.parse_nomis(csv_text)["E1"] == {"households": 100, "owned": 62, "social": 20, "private": 18}


def test_osm_parse_types_phone_and_chain():
    els = [{"type": "node", "id": 1, "lat": 51.5, "lon": 0.3,
            "tags": {"name": "Gold Ltd", "shop": "jewelry", "phone": "+44 1375 000000;+44 7000", "addr:street": "High St"}},
           {"type": "way", "id": 2, "center": {"lat": 51.5, "lon": 0.31},
            "tags": {"name": "Tesco Express", "shop": "convenience", "brand": "Tesco"}},
           {"type": "node", "id": 3, "lat": 51.5, "lon": 0.3, "tags": {"shop": "bakery"}}]
    a, b = osm.parse(els, "2026-11-05")
    assert a["btype"] == "Jeweller" and a["phone"] == "+44 1375 000000" and not a["chain"]
    assert b["chain"] == 1 and b["lat"] == 51.5


def test_door_history_labels():
    assert landreg_history.door_label("12", "") == "12"
    assert landreg_history.door_label("RIVERSIDE HEIGHTS", "FLAT 3") == "RIVERSIDE HEIGHTS"
    rows = ['{X},"200000","2020-01-01 00:00","RM18 7AA","T","N","F","12","","DOCK ROAD","","TILBURY","THURROCK","THURROCK","A","A"',
            '{Y},"200000","2020-01-01 00:00","SW1A 1AA","T","N","F","1","","DOWNING ST","","LONDON","X","X","A","A"']
    assert list(landreg_history.parse_lines(rows, ["RM18"])) == [("DOCK ROAD", "12", "RM18 7AA")]


def test_finalize_weights_by_ownership_and_sorts_doors():
    leads = [{"key": "A|T", "score": 10.0, "talking_points": [], "new_owner_doors": ["7"]},
             {"key": "B|T", "score": 10.0, "talking_points": []}]
    out = finalize_streets(leads, {"A|T": 0.2, "B|T": 0.8}, {"A|T": ["10", "2", "ROSE COTTAGE"]})
    assert [l["key"] for l in out] == ["B|T", "A|T"]
    assert out[1]["doors"] == ["2", "7", "10", "ROSE COTTAGE"]
