from flask import Flask, request, jsonify
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import binascii
import requests
import src.my_pb2 as my_pb2
import src.output_pb2 as output_pb2
import jwt

app = Flask(__name__)

AES_KEY = b'Yg&tc%DEuh6%Zc^8'
AES_IV = b'6oyZDr22E3ychjM%'

def encrypt_message(plaintext):
    cipher = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
    padded_message = pad(plaintext, AES.block_size)
    return cipher.encrypt(padded_message)

def fetch_open_id(access_token):
    try:
    
        uid_url = "https://prod-api.reward.ff.garena.com/redemption/api/auth/inspect_token/"
        uid_headers = {
            "authority": "prod-api.reward.ff.garena.com",
            "method": "GET",
            "path": "/redemption/api/auth/inspect_token/",
            "scheme": "https",
            "accept": "application/json, text/plain, */*",
            "accept-encoding": "gzip, deflate, br",
            "accept-language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "access-token": access_token,
            "cookie": "_gid=GA1.2.444482899.1724033242; _ga_XB5PSHEQB4=GS1.1.1724040177.1.1.1724040732.0.0.0; token_session=cb73a97aaef2f1c7fd138757dc28a08f92904b1062e66c; _ga_KE3SY7MRSD=GS1.1.1724041788.0.0.1724041788.0; _ga_RF9R6YT614=GS1.1.1724041788.0.0.1724041788.0; _ga=GA1.1.1843180339.1724033241; apple_state_key=817771465df611ef8ab00ac8aa985783; _ga_G8QGMJPWWV=GS1.1.1724049483.1.1.1724049880.0.0; datadome=HBTqAUPVsbBJaOLirZCUkN3rXjf4gRnrZcNlw2WXTg7bn083SPey8X~ffVwr7qhtg8154634Ee9qq4bCkizBuiMZ3Qtqyf3Isxmsz6GTH_b6LMCKWF4Uea_HSPk;",
            "origin": "https://reward.ff.garena.com",
            "referer": "https://reward.ff.garena.com/",
            "sec-ch-ua": '"Not.A/Brand";v="99", "Chromium";v="124"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Android"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        }

        uid_res = requests.get(uid_url, headers=uid_headers)
        uid_data = uid_res.json()
        uid = uid_data.get("uid")

        if not uid:
            return None, "Failed to extract UID"

        
        openid_url = "https://shop2game.com/api/auth/player_id_login"
        openid_headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ar-MA,ar;q=0.9,en-US;q=0.8,en;q=0.7,ar-AE;q=0.6,fr-FR;q=0.5,fr;q=0.4",
            "Connection": "keep-alive",
            "Content-Type": "application/json",
            "Cookie": "source=mb; region=MA; mspid2=ca21e6ccc341648eea845c7f94b92a3c; language=ar; _ga=GA1.1.1955196983.1741710601; datadome=WY~zod4Q8I3~v~GnMd68u1t1ralV5xERfftUC78yUftDKZ3jIcyy1dtl6kdWx9QvK9PpeM~A_qxq3LV3zzKNs64F_TgsB5s7CgWuJ98sjdoCqAxZRPWpa8dkyfO~YBgr; session_key=v0tmwcmf1xqkp7697hhsno0di1smy3dm; _ga_0NY2JETSPJ=GS1.1.1741710601.1.1.1741710899.0.0.0",
            "Origin": "https://shop2game.com",
            "Referer": "https://shop2game.com/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Mobile Safari/537.36",
            "sec-ch-ua-mobile": "?1",
            "sec-ch-ua-platform": '"Android"'
        }
        payload = {
            "app_id": 100067,
            "login_id": str(uid)
        }

        openid_res = requests.post(openid_url, headers=openid_headers, json=payload)
        openid_data = openid_res.json()
        open_id = openid_data.get("open_id")

        if not open_id:
            return None, "Failed to extract open_id"

        return open_id, None

    except Exception as e:
        return None, f"Exception occurred: {str(e)}"

@app.route('/access-jwt', methods=['GET'])
def majorlogin_jwt():
    access_token = request.args.get('access_token')
    provided_open_id = request.args.get('open_id')

    if not access_token:
        return jsonify({"message": "missing access_token"}), 400

    open_id = provided_open_id
    if not open_id:
        open_id, error = fetch_open_id(access_token)
        if error:
            return jsonify({"message": error}), 400

    platforms = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]  

    for platform_type in platforms:
        game_data = my_pb2.GameData()
        game_data.timestamp = "2024-12-05 18:15:32"
        game_data.game_name = "free fire"
        game_data.game_version = 1
        game_data.version_code = "1.132.1"
        game_data.os_info = "Android OS 9 / API-28 (PI/rel.cjw.20220518.114133)"
        game_data.device_type = "Handheld"
        game_data.network_provider = "Verizon Wireless"
        game_data.connection_type = "WIFI"
        game_data.screen_width = 1280
        game_data.screen_height = 960
        game_data.dpi = "240"
        game_data.cpu_info = "ARMv7 VFPv3 NEON VMH | 2400 | 4"
        game_data.total_ram = 5951
        game_data.gpu_name = "Adreno (TM) 640"
        game_data.gpu_version = "OpenGL ES 3.0"
        game_data.user_id = "Google|74b585a9-0268-4ad3-8f36-ef41d2e53610"
        game_data.ip_address = "172.190.111.97"
        game_data.language = "en"
        game_data.open_id = open_id
        game_data.access_token = access_token
        game_data.platform_type = platform_type
        game_data.field_99 = str(platform_type)
        game_data.field_100 = str(platform_type)

        serialized_data = game_data.SerializeToString()
        encrypted_data = encrypt_message(serialized_data)
        hex_encrypted_data = binascii.hexlify(encrypted_data).decode('utf-8')

        url = "https://loginbp.ppmainecoonghj.com///MajorLogin"
        headers = {
            "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
            "Connection": "Keep-Alive",
            "Accept-Encoding": "gzip",
            "Content-Type": "application/octet-stream",
            "Expect": "100-continue",
            "X-Unity-Version": "2018.4.11f1",
            "X-GA": "v1 1",
            "ReleaseVersion": "OB55"
        }
        edata = bytes.fromhex(hex_encrypted_data)

        try:
            response = requests.post(url, data=edata, headers=headers, verify=False, timeout=5)

            if response.status_code == 200:
                data_dict = None
                try:
                    example_msg = output_pb2.Garena_420()
                    example_msg.ParseFromString(response.content)
                    data_dict = {field.name: getattr(example_msg, field.name)
                                 for field in example_msg.DESCRIPTOR.fields
                                 if field.name not in ["binary", "binary_data", "Garena420"]}
                except Exception:
                    try:
                        data_dict = response.json()
                    except ValueError:
                        continue  

                if data_dict and "token" in data_dict:
                    token_value = data_dict["token"]
                    try:
                        decoded_token = jwt.decode(token_value, options={"verify_signature": False})
                    except Exception as e:
                        decoded_token = {}

                    result = {
                        "account_id": decoded_token.get("account_id"),
                        "account_name": decoded_token.get("nickname"),
                        "open_id": open_id,
                        "access_token": access_token,
                        "platform": decoded_token.get("external_type"),
                        "region": decoded_token.get("lock_region"),
                        "status": "success",
                        "token": token_value
                    }
                    return jsonify(result), 200
        except requests.RequestException:
            continue  

    return jsonify({"message": "No valid platform found"}), 400


@app.route('/info', methods=['GET'])
def oauth_guest():
    uid = request.args.get('uid')
    if not uid:
        return jsonify({"message": "Missing uid"}), 400

    import uuid
    oauth_url = "https://100067.connect.garena.com/oauth/guest/token/grant"
    payload = {
        'grant_type': "guest",
        'client_id': "100067",
        'client_secret': "6393b3f2ec55079a0224be618be464f14122cc7b5d19db911c4d9a26372d82bf",
        'device_id': uuid.uuid4().hex + '00000000'
    }
    
    try:
        oauth_response = requests.post(oauth_url, data=payload, timeout=5)
    except requests.RequestException as e:
        return jsonify({"message": str(e)}), 500

    if oauth_response.status_code != 200:
        try:
            return jsonify(oauth_response.json()), oauth_response.status_code
        except ValueError:
            return jsonify({"message": oauth_response.text}), oauth_response.status_code

    try:
        oauth_data = oauth_response.json()
    except ValueError:
        return jsonify({"message": "Invalid JSON response from OAuth service"}), 500

    if 'access_token' not in oauth_data or 'open_id' not in oauth_data:
        return jsonify({"message": "OAuth response missing access_token or open_id"}), 500

    params = {
        'access_token': oauth_data['access_token'],
        'open_id': oauth_data['open_id']
    }
    
    with app.test_request_context('/api/info', query_string=params):
        return majorlogin_jwt()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=1080, debug=False)

#app.py is full code and the text code is main code . now your work is i want to see the  ( "AccountLevel": ) this in my main code
