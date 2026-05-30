#!/usr/bin/env python3
"""
Fetch active sale listings from RentCast API for Hudson Valley ZIPs.
Saves one JSON file per ZIP to data/rentcast_hv/.
Skips ZIPs already fetched (resume-safe).
"""

import json
import os
import sys
import time
from pathlib import Path

import ssl
import urllib.request
import urllib.error

import certifi
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

API_KEY = os.environ.get("RENTCAST_API_KEY")
if not API_KEY:
    sys.exit("Set RENTCAST_API_KEY env variable first")

HV_ZIPS = [
    "10501","10502","10503","10504","10505","10506","10507","10509","10510",
    "10511","10512","10514","10516","10517","10518","10519","10520","10522",
    "10523","10524","10526","10527","10528","10530","10532","10533","10535",
    "10536","10537","10538","10540","10541","10542","10543","10545","10546",
    "10547","10548","10549","10550","10552","10553","10560","10562","10566",
    "10567","10570","10573","10576","10577","10578","10579","10580","10583",
    "10588","10589","10590","10591","10594","10595","10596","10597","10598",
    "10601","10603","10604","10605","10606","10607","10701","10703","10704",
    "10705","10706","10707","10708","10709","10710","10801","10803","10804",
    "10805","10901","10910","10911","10913","10914","10915","10916","10917",
    "10918","10919","10920","10921","10922","10923","10924","10925","10926",
    "10927","10928","10930","10931","10932","10933","10940","10941","10950",
    "10952","10953","10954","10956","10958","10960","10962","10963","10964",
    "10965","10968","10969","10970","10973","10974","10975","10976","10977",
    "10979","10980","10983","10984","10985","10986","10987","10988","10989",
    "10990","10992","10993","10994","10996","10998","12518","12520","12543",
    "12549","12550","12553","12563","12575","12577","12586","12729","12746",
    "12771","12780",
]

OUT_DIR = Path(__file__).parent.parent / "data" / "rentcast_hv"
OUT_DIR.mkdir(parents=True, exist_ok=True)

fetched = skipped = errors = total_listings = 0

for i, zip_code in enumerate(HV_ZIPS, 1):
    out_file = OUT_DIR / f"rentcast_{zip_code}.json"
    if out_file.exists():
        skipped += 1
        print(f"[{i}/{len(HV_ZIPS)}] {zip_code}: already fetched, skipping")
        continue

    url = f"https://api.rentcast.io/v1/listings/sale?zipCode={zip_code}&status=Active&limit=500"
    req = urllib.request.Request(url, headers={"X-Api-Key": API_KEY})

    try:
        with urllib.request.urlopen(req, timeout=30, context=SSL_CONTEXT) as resp:
            body = resp.read()
        data = json.loads(body)
        out_file.write_bytes(body)
        n = len(data) if isinstance(data, list) else 0
        total_listings += n
        fetched += 1
        print(f"[{i}/{len(HV_ZIPS)}] {zip_code}: {n} listings")
    except urllib.error.HTTPError as e:
        if e.code == 429:
            print(f"[{i}/{len(HV_ZIPS)}] {zip_code}: rate limited — sleeping 60s")
            time.sleep(60)
            # retry once
            try:
                with urllib.request.urlopen(req, timeout=30, context=SSL_CONTEXT) as resp:
                    body = resp.read()
                data = json.loads(body)
                out_file.write_bytes(body)
                n = len(data) if isinstance(data, list) else 0
                total_listings += n
                fetched += 1
                print(f"[{i}/{len(HV_ZIPS)}] {zip_code}: {n} listings (retry ok)")
            except Exception as e2:
                errors += 1
                print(f"[{i}/{len(HV_ZIPS)}] {zip_code}: retry failed: {e2}")
        else:
            errors += 1
            print(f"[{i}/{len(HV_ZIPS)}] {zip_code}: HTTP {e.code} {e.reason}")
    except Exception as e:
        errors += 1
        print(f"[{i}/{len(HV_ZIPS)}] {zip_code}: error: {e}")

    # polite rate limit: 1 request/second
    time.sleep(1)

print(f"\nDone. Fetched: {fetched}, Skipped: {skipped}, Errors: {errors}")
print(f"Total listings across all ZIPs: {total_listings}")
