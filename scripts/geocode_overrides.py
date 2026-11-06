#!/usr/bin/env python3
"""One-time script to geocode unmatched station cities via Nominatim.

Conforms to docs/ARCHITECTURE.md §5.1.
Throttled to <= 1 req/s, descriptive User-Agent.
Writes to backend/apps/stations/data/geocode_overrides.csv.
"""

import csv
import re
import time

import httpx

US_STATES = {
    "AL",
    "AK",
    "AZ",
    "AR",
    "CA",
    "CO",
    "CT",
    "DE",
    "FL",
    "GA",
    "HI",
    "ID",
    "IL",
    "IN",
    "IA",
    "KS",
    "KY",
    "LA",
    "ME",
    "MD",
    "MA",
    "MI",
    "MN",
    "MS",
    "MO",
    "MT",
    "NE",
    "NV",
    "NH",
    "NJ",
    "NM",
    "NY",
    "NC",
    "ND",
    "OH",
    "OK",
    "OR",
    "PA",
    "RI",
    "SC",
    "SD",
    "TN",
    "TX",
    "UT",
    "VT",
    "VA",
    "WA",
    "WV",
    "WI",
    "WY",
    "DC",
}


def clean_place(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"\(balance\)", "", s)
    s = re.sub(
        r"\b(county|city|town|township|cdp|village|borough|charter township|plantation|metropolitan government|unified government|consolidated government)\b",
        "",
        s,
    )
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\bst\b", "saint", s)
    s = re.sub(r"\bste\b", "sainte", s)
    s = re.sub(r"\bft\b", "fort", s)
    s = re.sub(r"\bmt\b", "mount", s)
    s = s.replace(" ", "")
    return s


def main() -> None:
    # 1. Load us_places.csv
    known = set()
    with open("backend/apps/stations/data/us_places.csv", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            known.add((r["city_norm"], r["state"]))

    # 2. Find unmatched
    with open("data/fuel-prices-for-be-assessment.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    unmatched: dict[tuple[str, str], str] = {}
    for r in rows:
        st = r["State"].strip().upper()
        if st not in US_STATES:
            continue
        try:
            p = float(r["Retail Price"].strip())
            if p <= 0 or p > 20:
                continue
        except ValueError:
            continue
        city_raw = r["City"].strip()
        c_norm = clean_place(city_raw)
        if (c_norm, st) not in known:
            unmatched[(c_norm, st)] = city_raw

    print(f"Total unmatched unique cities to geocode: {len(unmatched)}")

    headers = {
        "User-Agent": "FuelRoute-Importer/1.0 (https://github.com/example/fuelroute; contact@fuelroute.org)"
    }
    client = httpx.Client(headers=headers, timeout=10.0)

    overrides = []
    # If overrides file already exists, read existing
    try:
        with open(
            "backend/apps/stations/data/geocode_overrides.csv", encoding="utf-8"
        ) as f:
            reader = csv.DictReader(f)
            for r in reader:
                overrides.append(
                    (r["city_norm"], r["state"], float(r["lat"]), float(r["lon"]))
                )
                unmatched.pop((r["city_norm"], r["state"]), None)
    except FileNotFoundError:
        pass

    print(f"Remaining after existing overrides: {len(unmatched)}")
    count = 0
    for (c_norm, st), city_raw in sorted(unmatched.items()):
        query = f"{city_raw}, {st}, USA"
        url = "https://nominatim.openstreetmap.org/search"
        params = {"q": query, "format": "jsonv2", "limit": 1, "countrycodes": "us"}
        try:
            time.sleep(1.1)  # Strict rate limit: <= 1 req/s
            resp = client.get(url, params=params)
            if resp.status_code == 200:
                data = resp.json()
                if data:
                    lat = round(float(data[0]["lat"]), 6)
                    lon = round(float(data[0]["lon"]), 6)
                    overrides.append((c_norm, st, lat, lon))
                    count += 1
                    print(f"[{count}/{len(unmatched)}] Found {query} -> ({lat}, {lon})")
                else:
                    print(f"[{count}/{len(unmatched)}] No match for {query}")
            else:
                print(f"HTTP {resp.status_code} for {query}")
        except httpx.HTTPError as e:
            print(f"Error querying {query}: {e}")

    out_file = "backend/apps/stations/data/geocode_overrides.csv"
    with open(out_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["city_norm", "state", "lat", "lon"])
        for c_norm, st, lat, lon in sorted(overrides):
            writer.writerow([c_norm, st, lat, lon])

    print(f"Done! Wrote {len(overrides)} overrides to {out_file}")


if __name__ == "__main__":
    main()
