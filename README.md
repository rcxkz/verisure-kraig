# Essex Lead Finder (Phase 1)

A daily list of streets to door-knock and businesses to visit or call, around Tilbury and South Essex, built from public data.

## Run it

```bash
pip install -r requirements.txt
python -m leadfinder run        # fetch + score + write today's report (~40s first time, faster after)
```

Open `output/<date>/report.html` on a phone or laptop. The same folder also has `streets.csv`, `businesses.csv` and `leads.json`.

## Log what happened at each door

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
| HM Land Registry Price Paid | Recent house sales = new homeowners (house numbers) | Monthly |
| Food Standards Agency | New food businesses awaiting first inspection | Daily |
| Companies House (optional) | Newly incorporated shops, salons, cafés, garages | Daily. Needs a free key: `export COMPANIES_HOUSE_API_KEY=...` |

## Tuning

- **Patch:** towns, postcode districts and councils are in `config.toml`.
- **No Cold Calling Zones:** add them under `[exclusions]` in `config.toml`.
- **Scoring weights:** at the top of `leadfinder/scoring.py`.
- **Tests:** `python -m pytest tests`

## Ground rules

- Talk about the area, never a named victim or a specific burgled house.
- Police locations are approximate ("on or near"). Quote them that way.
- Check phone numbers against the TPS (people) and CTPS (businesses) before calling.
