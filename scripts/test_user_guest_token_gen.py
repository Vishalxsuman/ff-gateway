# -*- coding: utf-8 -*-
"""
test_user_guest_token_gen.py — End-to-end verification script for user's guest credentials.

Flow:
 1. OAuth grant using user's FF_GUEST_UID & FF_GUEST_PASSWORD
 2. AES-128-CBC Protobuf MajorLogin to generate fresh Garena Session JWT
 3. Use generated JWT to fetch real player telemetry from Garena servers (UID 2112210696)
"""

import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ff import auth, client


def main():
    print("==================================================")
    print("ESPORIZON GUEST AUTH & LIVE TELEMETRY VERIFICATION")
    print("==================================================")

    # 1. Trigger live login using user's guest credentials
    token, expires_at = auth._do_login()
    print(f"\n[1] Fresh Garena Session JWT Generated from User Guest Account:")
    print(f"    Token: {token[:60]}...")
    print(f"    Expires in: {round((expires_at - auth.time.time()) / 3600, 2)} hours")

    # 2. Update active token in gateway
    update_res = auth.update_token(token)
    print(f"\n[2] Updated Gateway Token State: {update_res}")

    # 3. Test querying real Free Fire player telemetry with the generated JWT
    test_uid = 2112210696
    region = "IND"
    print(f"\n[3] Querying Garena {region} server for UID {test_uid} using generated JWT...")

    try:
        player_data = client.fetch_player(test_uid, region)
        print("\n[SUCCESS] LIVE TELEMETRY DECRYPTED SUCCESSFULLY:")
        print(f"  - Nickname: {player_data.get('basic_info', {}).get('nickname')}")
        print(f"  - Level (AccountLevel): {player_data.get('basic_info', {}).get('AccountLevel')}")
        print(f"  - BR Rank Points: {player_data.get('rank_info', {}).get('br_ranking_points')}")
        print(f"  - CS Rank Points: {player_data.get('rank_info', {}).get('cs_ranking_points')}")
        print(f"  - Credit Score: {player_data.get('credit_score_info', {}).get('score')}")
        print(f"  - Clan Name: {player_data.get('clan_info', {}).get('clan_name')}")
        print("\nFull Response Object Preview:")
        print(json.dumps(player_data, indent=2))
    except Exception as exc:
        print(f"\n[ERROR] Live query failed: {exc}")


if __name__ == "__main__":
    main()
