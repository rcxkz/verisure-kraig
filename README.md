# Essex Lead Finder (Phase 1)

A daily list of streets to door-knock and businesses to visit or call, around Tilbury and South Essex, built from public data.

## Run it

```bash
pip install -r requirements.txt
python -m leadfinder run        # fetch + score + write today's report (~40s first time, faster after)
```

Open `output/<date>/report.html` on a phone or laptop. The same folder also has `streets.csv`, `businesses.csv` and `leads.json`.

## Mobile app

Every run also builds an installable phone app in `output/site/`:

```bash
python -m http.server -d output/site 8000   # then open http://<this-computer>:8000 on the phone
```

- **Streets:** cards with talking points, **Go** (walking directions), **Knock doors**, **Skip**, and **Near me** to sort by distance.
- **Street screen** (tap a street card): one row per house number with **Out / ✗ / ✓** tick buttons. ✓ asks Callback / Appointment / Sold, plus a note. Tapping a lit tick again clears it. It has Odd / Even / All filters, a "Doors 1 to N" range, **+ Add** for flats and lettered doors, and NEW OWNER tags from recent sales. Tap a number for more options, like the No cold callers sign. **Finish street** hides the street for 21 days.
- **Map:** scored streets (red), new businesses (blue) and recent burglaries (grey dots).
- **Shops:** new businesses with a "Phone / hours" lookup, plus the shop streets with the most theft.
- **Log:** Doors / Appointments / Sold / Installs by **Day, Week or Month**, with a per-day or per-week breakdown. It also has callbacks due (with a badge on the tab), sold-awaiting-install with **Mark installed**, history, CSV export, and a **Feedback** form.
- **Feedback** posts to `functions/api/feedback.js`, which runs on Cloudflare behind the Access login and opens a private GitHub issue. It needs the Pages secret `GITHUB_TOKEN`: a fine-grained token with Issues read & write on this repo only.
- To install it, use "Add to Home Screen" in Safari or Chrome.

Visits are stored on the phone for now. Syncing them to a database is the next step.

## Log from the command line

```bash
python -m leadfinder log street "DOCK ROAD|Tilbury" not_home
python -m leadfinder log street "DOCK ROAD|Tilbury" callback --note "come back after 6pm"
python -m leadfinder log business fsa:1234567 appointment
python -m leadfinder history
```

Outcomes: `not_home`, `not_interested`, `callback`, `appointment`, `sold`, `do_not_return`.
A logged street or business is hidden for 21 days. One logged as `sold` or `do_not_return` is hidden for good.

## Data sources

| Source | Gives | Updates |
|---|---|---|
| data.police.uk | Burglary, robbery, vehicle crime, shoplifting by street | Monthly, ~2 month lag |
| Google News RSS | Local crime stories naming a town in the patch | Daily |
| HM Land Registry (last 6 months) | Recent sales = new owners, plus new-build flag | Monthly |
| HM Land Registry (10 years) | Real house numbers / names per street for the door list | Every 120 days |
| PlanIt (planit.org.uk) | Planning applications: extensions, new homes, business change of use | Daily |
| Census 2021 (Nomis, TS054) | % owner-occupied around each street, used to weight the score | Static, cached |
| Food Standards Agency | New food businesses awaiting first inspection | Daily |
| OpenStreetMap (Overpass) | Every named shop / pub / garage / salon, often with phone and hours | Daily |

**Checked and deliberately not used:**
- **EPC register:** its address data is licensed for energy-efficiency purposes only.
- **VOA business rates list:** restricted to business-rates purposes only.
- **Essex Community Messaging:** email alerts only. Kraig should subscribe himself.

## Tuning

- **Patch:** towns, postcode districts and councils are in `config.toml`.
- **No Cold Calling Zones:** add them under `[exclusions]` in `config.toml`.
- **Scoring weights:** at the top of `leadfinder/scoring.py`.
- **Tests:** `python -m pytest tests`

## Ground rules

- Talk about the area, never a named victim or a specific burgled house.
- Police locations are approximate ("on or near"). Quote them that way.
- Check phone numbers against the TPS (people) and CTPS (businesses) before calling.
