# -*- coding: utf-8 -*-
import json
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ff import auth, client

def main():
    print("==================================================")
    print("ESPORIZON FREE FIRE LIVE TELEMETRY CMD INSPECTOR")
    print("==================================================")

    # 1. Load active token
    token = auth.get_token()
    print(f"[1] Active Session JWT Loaded (starts with: {token[:40]}...)")

    # 2. Target UID & Region
    uid = 2112210696
    region = "IND"
    print(f"[2] Querying Garena {region} server for UID {uid}...")

    # 3. Call Garena API directly
    try:
        data = client.fetch_player(uid, region)
        print("\n[SUCCESS] LIVE TELEMETRY RETRIEVED SUCCESSFULLY FROM GARENA SERVER:\n")
        print(json.dumps(data, indent=2))
    except Exception as exc:
        print(f"\n[ERROR] Garena Request Error: {exc}")

if __name__ == "__main__":
    main()
