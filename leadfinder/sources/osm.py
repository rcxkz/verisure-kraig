"""Every mapped shop / pub / garage / salon in the patch from OpenStreetMap (ODbL — © OpenStreetMap contributors).

OSM often has phone numbers and opening hours. Chains (tagged with a brand) are kept but
ranked lower, since head office usually decides on security.
"""
from datetime import date

from .fsa import upsert

OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]

AMENITIES = "pub|bar|restaurant|cafe|fast_food|pharmacy|dentist|veterinary|car_wash|fuel|bureau_de_change|nightclub"

TYPE_NAMES = {
    "jewelry": "Jeweller", "mobile_phone": "Phone shop", "e-cigarette": "Vape shop", "alcohol": "Off-licence",
    "convenience": "Convenience store", "chemist": "Chemist", "pharmacy": "Pharmacy", "car_repair": "Garage",
    "car": "Car dealer", "car_parts": "Car parts", "tyres": "Tyres", "hairdresser": "Hairdresser", "beauty": "Beauty salon",
    "barber": "Barber", "pawnbroker": "Pawnbroker", "money_lender": "Money lender", "electronics": "Electronics",
    "computer": "Computer shop", "tobacco": "Tobacconist", "pub": "Pub", "bar": "Bar", "nightclub": "Nightclub",
    "restaurant": "Restaurant", "cafe": "Café", "fast_food": "Takeaway", "dentist": "Dentist", "veterinary": "Vet",
    "fuel": "Petrol station", "car_wash": "Car wash", "bureau_de_change": "Bureau de change", "bakery": "Bakery",
    "butcher": "Butcher", "florist": "Florist", "clothes": "Clothes shop", "furniture": "Furniture shop",
    "hardware": "Hardware / DIY", "doityourself": "Hardware / DIY", "bicycle": "Bike shop", "pet": "Pet shop",
    "optician": "Optician", "newsagent": "Newsagent", "dry_cleaning": "Dry cleaner", "laundry": "Launderette",
    "kitchen": "Kitchen showroom", "bathroom_furnishing": "Bathroom showroom", "motorcycle": "Motorbike shop",
}
# How strong a security prospect each type is
WEIGHT = {"Jeweller": 5, "Pawnbroker": 5, "Phone shop": 4, "Vape shop": 4, "Off-licence": 4, "Tobacconist": 4,
          "Electronics": 4, "Computer shop": 4, "Garage": 4, "Car dealer": 4, "Car parts": 3, "Tyres": 3,
          "Pharmacy": 4, "Chemist": 3, "Convenience store": 3, "Newsagent": 3, "Bureau de change": 4,
          "Money lender": 4, "Bike shop": 4, "Motorbike shop": 4, "Pub": 3, "Bar": 3, "Nightclub": 3,
          "Petrol station": 3, "Hairdresser": 2, "Barber": 2, "Beauty salon": 2, "Takeaway": 2, "Restaurant": 2,
          "Café": 2, "Dentist": 2, "Vet": 2, "Optician": 3, "Hardware / DIY": 3}


def query(bbox):
    s, w, n, e = bbox
    b = f"({s},{w},{n},{e})"
    return (f'[out:json][timeout:180];(nwr["shop"]["name"]{b};nwr["amenity"~"^({AMENITIES})$"]["name"]{b};'
            f'nwr["craft"]["name"]{b};);out center tags;')


def bbox(towns, pad=0.025):
    return (min(t["lat"] for t in towns) - pad, min(t["lng"] for t in towns) - pad,
            max(t["lat"] for t in towns) + pad, max(t["lng"] for t in towns) + pad)


def parse(elements, today):
    out = []
    for el in elements:
        t = el.get("tags") or {}
        name = t.get("name")
        lat = el.get("lat", (el.get("center") or {}).get("lat"))
        lng = el.get("lon", (el.get("center") or {}).get("lon"))
        if not name or lat is None:
            continue
        raw = t.get("shop") or t.get("amenity") or t.get("craft") or ""
        if raw in ("vacant", "no", "yes") and "craft" not in t:
            continue
        kind = TYPE_NAMES.get(raw, raw.replace("_", " ").capitalize() or "Business")
        addr = " ".join(x for x in (t.get("addr:housenumber"), t.get("addr:street")) if x)
        chain = t.get("brand") or t.get("brand:wikidata")
        sig = "Chain store — head office usually decides" if chain else "Independent local business (OpenStreetMap)"
        if t.get("opening_hours"):
            sig += f" · hours: {t['opening_hours'][:60]}"
        out.append({
            "source": "osm", "ext_id": f"{el['type']}/{el['id']}", "name": name, "btype": kind,
            "address": addr or t.get("addr:place", ""), "postcode": t.get("addr:postcode", ""),
            "lat": float(lat), "lng": float(lng), "signal": sig, "signal_date": None, "today": today,
            "phone": (t.get("phone") or t.get("contact:phone") or "").split(";")[0].strip(),
            "chain": 1 if chain else 0,
        })
    return out


def fetch(conn, sess, cfg, log):
    q = query(bbox(cfg["towns"]))
    last = None
    for url in OVERPASS:
        try:
            r = sess.post(url, data={"data": q}, timeout=240)
            r.raise_for_status()
            elements = r.json()["elements"]
            break
        except Exception as e:  # try the mirror
            last = e
    else:
        raise last
    today = date.today().isoformat()
    total = new = 0
    for b in parse(elements, today):
        total += 1
        new += upsert(conn, b)
    conn.commit()
    log(f"openstreetmap: {total} named businesses ({new} first seen)")
    return {"total": total}
