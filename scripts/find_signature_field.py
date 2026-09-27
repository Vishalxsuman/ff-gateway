# -*- coding: utf-8 -*-
import sys
import requests
import re
import base64
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ff import auth
from src.ff.protobuf import my_pb2
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

open_id = "29f3c09513f42bc0c5f0d7ce3705c558"
access_token = "ecd369b62eb8a9497cba801ab87e44e00b50c447cf0a833dbb8d8a0cfdd28fdf"
SIG = "7428b253defc164018c604a1ebbfebdf"

gd_base = my_pb2.GameData()
gd_base.timestamp = "2024-12-05 18:15:32"
gd_base.game_name = "free fire"
gd_base.game_version = 1
gd_base.version_code = "1.132.8"
gd_base.os_info = "Android OS 9 / API-28"
gd_base.device_type = "Handheld"
gd_base.device_form_factor = "Handheld"
gd_base.device_model = "ASUS_Z01QD"
gd_base.network_provider = "Verizon"
gd_base.connection_type = "WIFI"
gd_base.screen_width = 1280
gd_base.screen_height = 960
gd_base.dpi = "240"
gd_base.cpu_info = "ARMv7"
gd_base.total_ram = 5951
gd_base.gpu_name = "Adreno 640"
gd_base.gpu_version = "OpenGL ES 3.0"
gd_base.user_id = "Google|114797439734039373833"
gd_base.ip_address = "172.190.111.97"
gd_base.language = "en"
gd_base.open_id = open_id
gd_base.access_token = access_token
gd_base.platform_type = 8
gd_base.build_number = "2019121229"
gd_base.marketplace = "google"
gd_base.field_99 = "8"
gd_base.field_100 = "8"

string_fields = [f.name for f in gd_base.DESCRIPTOR.fields if f.type == 9 and f.name not in ('open_id', 'access_token', 'game_name')]

for fname in string_fields:
    gd = my_pb2.GameData()
    gd.CopyFrom(gd_base)
    setattr(gd, fname, SIG)

    sdata = gd.SerializeToString()
    cipher = AES.new(b"Yg&tc%DEuh6%Zc^8", AES.MODE_CBC, b"6oyZDr22E3ychjM%")
    edata = cipher.encrypt(pad(sdata, 16))

    mheaders = {
        "User-Agent": "UnityPlayer/2018.4.12f1 (UnityWebRequest/1.0, libcurl/8.5.0-DEV)",
        "Content-Type": "application/octet-stream",
        "X-Unity-Version": "2018.4.12f1",
        "X-GA": "v1 1",
        "X-GA-SV": "1790540006",
        "ReleaseVersion": "OB55",
        "Authorization": f"Bearer {access_token}"
    }

    try:
        mr = requests.post("https://loginbp.ppmainecoonghj.com/MajorLogin", data=edata, headers=mheaders, timeout=5)
        idx = mr.content.find(b"eyJ")
        if idx != -1:
            jwt_raw = mr.content[idx:].decode("utf-8", errors="ignore")
            m = re.search(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", jwt_raw)
            if m:
                tok = m.group(0)
                p = tok.split(".")[1]
                p += "=" * (-len(p) % 4)
                data = json.loads(base64.urlsafe_b64decode(p))
                sig = data.get("signature_md5")
                print(f"Testing GameData.{fname} = SIG -> signature_md5 in JWT: '{sig}'")
                if sig:
                    print(f"\n==================================================")
                    print(f"🎉 SUCCESS! GameData.{fname} POPULATES signature_md5!")
                    print(f"==================================================")
                    break
    except Exception as exc:
        print(f"Error testing {fname}: {exc}")
