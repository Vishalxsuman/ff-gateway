# -*- coding: utf-8 -*-
import sys
import zipfile
import binascii
import requests
from pathlib import Path
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

# 1. Read protobuf files from zip
zpath = Path(r"f:\My Projects\Esporizon_v1\_archive\info\jwtapi.zip")
with zipfile.ZipFile(zpath) as z:
    my_pb2_code = z.read("jwtapi/my_pb2.py").decode("utf-8")
    output_pb2_code = z.read("jwtapi/output_pb2.py").decode("utf-8")

exec(my_pb2_code, globals())
exec(output_pb2_code, globals())

AES_KEY = b"Yg&tc%DEuh6%Zc^8"
AES_IV = b"6oyZDr22E3ychjM%"

def test_majorlogin():
    uid = "7943649152"
    pwd = "1219443E419AD8761270FCB2CF0649AF2C40A6B0286F9466E16DC4D09CED42D3"
    
    # Step 1: OAuth grant
    oauth_url = "https://ffmconnect.live.gop.garenanow.com/oauth/guest/token/grant"
    payload = {
        "uid": uid,
        "password": pwd,
        "response_type": "token",
        "client_type": "2",
        "client_secret": "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3",
        "client_id": "100067"
    }
    headers = {
        "User-Agent": "GarenaMSDK/4.0.19P9(SM-M526B ;Android 13;pt;BR;)",
        "Connection": "Keep-Alive"
    }
    
    r = requests.post(oauth_url, data=payload, headers=headers, timeout=10)
    odata = r.json()
    open_id = odata.get("open_id")
    access_token = odata.get("access_token")
    print(f"[1] OAuth Grant Success: open_id={open_id[:8]}... access_token={access_token[:8]}...")

    # Step 2: Protobuf MajorLogin
    platforms = [4]
    for plat in platforms:
        gd = GameData()
        gd.timestamp = "2024-12-05 18:15:32"
        gd.game_name = "free fire"
        gd.game_version = 1
        gd.version_code = "1.132.1"
        gd.os_info = "Android OS 9 / API-28"
        gd.device_type = "Handheld"
        gd.network_provider = "Verizon"
        gd.connection_type = "WIFI"
        gd.screen_width = 1280
        gd.screen_height = 960
        gd.dpi = "240"
        gd.cpu_info = "ARMv7"
        gd.total_ram = 5951
        gd.gpu_name = "Adreno 640"
        gd.gpu_version = "OpenGL ES 3.0"
        gd.user_id = "Google|74b585a9"
        gd.ip_address = "172.190.111.97"
        gd.language = "en"
        gd.open_id = open_id
        gd.access_token = access_token
        gd.platform_type = plat
        gd.field_99 = str(plat)
        gd.field_100 = str(plat)

        sdata = gd.SerializeToString()
        cipher = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
        edata = cipher.encrypt(pad(sdata, 16))

        murl = "https://loginbp.ppmainecoonghj.com/MajorLogin"
        mheaders = {
            "User-Agent": "UnityPlayer/2018.4.12f1 (UnityWebRequest/1.0, libcurl/8.5.0-DEV)",
            "Content-Type": "application/octet-stream",
            "X-Unity-Version": "2018.4.12f1",
            "X-GA": "v1 1",
            "X-GA-SV": "1790540006",
            "ReleaseVersion": "OB55",
            "Authorization": f"Bearer {access_token}"
        }

        mr = requests.post(murl, data=edata, headers=mheaders, timeout=5)
        print(f"[2] Platform {plat} MajorLogin HTTP Status: {mr.status_code}")
        if mr.status_code == 200:
            out = Garena_420()
            out.ParseFromString(mr.content)
            tok = getattr(out, "token", "")
            print("\n==================================================")
            print("[SUCCESS] PERMANENT AUTOMATIC MAJORLOGIN SUCCESS!")
            print(f"Generated Garena Session JWT:\n{tok}")
            print("==================================================")
            return tok
        else:
            print(f"[400 Error Content]: {mr.content}")

if __name__ == "__main__":
    test_majorlogin()
