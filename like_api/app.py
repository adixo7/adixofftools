from flask import Flask, request, jsonify
import asyncio
import os
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from google.protobuf.json_format import MessageToJson
import binascii
import aiohttp
import requests
import json
import like_pb2
import like_count_pb2
import uid_generator_pb2
from google.protobuf.message import DecodeError

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def load_tokens(server_name):
    try:
        if server_name == "IND":
            path = os.path.join(BASE_DIR, "token_ind.json")
        elif server_name in {"BR", "US", "SAC", "NA"}:
            path = os.path.join(BASE_DIR, "token_br.json")
        else:
            path = os.path.join(BASE_DIR, "token_bd.json")
        with open(path, "r") as f:
            tokens = json.load(f)
        if not tokens:
            app.logger.error(f"Token file for {server_name} is empty.")
            return None
        return tokens
    except Exception as e:
        app.logger.error(f"Error loading tokens for server {server_name}: {e}")
        return None

def encrypt_message(plaintext):
    try:
        key = b'Yg&tc%DEuh6%Zc^8'
        iv = b'6oyZDr22E3ychjM%'
        cipher = AES.new(key, AES.MODE_CBC, iv)
        padded_message = pad(plaintext, AES.block_size)
        encrypted_message = cipher.encrypt(padded_message)
        return binascii.hexlify(encrypted_message).decode('utf-8')
    except Exception as e:
        app.logger.error(f"Error encrypting message: {e}")
        return None

def create_protobuf_message(user_id, region):
    try:
        message = like_pb2.like()
        message.uid = int(user_id)
        message.region = region
        return message.SerializeToString()
    except Exception as e:
        app.logger.error(f"Error creating protobuf message: {e}")
        return None

async def send_request(encrypted_uid, token, url):
    try:
        edata = bytes.fromhex(encrypted_uid)
        headers = {
            'User-Agent': "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
            'Connection': "Keep-Alive",
            'Accept-Encoding': "gzip",
            'Authorization': f"Bearer {token}",
            'Content-Type': "application/x-www-form-urlencoded",
            'Expect': "100-continue",
            'X-Unity-Version': "2018.4.11f1",
            'X-GA': "v1 1",
            'ReleaseVersion': "OB53"
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=edata, headers=headers) as response:
                if response.status != 200:
                    return response.status
                return await response.text()
    except Exception as e:
        app.logger.error(f"Exception in send_request: {e}")
        return None

async def send_multiple_requests(uid, server_name, url):
    try:
        region = server_name
        protobuf_message = create_protobuf_message(uid, region)
        if protobuf_message is None:
            return None
        encrypted_uid = encrypt_message(protobuf_message)
        if encrypted_uid is None:
            return None
        tokens = load_tokens(server_name)
        if tokens is None:
            return None
        tasks = []
        for i in range(100):
            token = tokens[i % len(tokens)]["token"]
            tasks.append(send_request(encrypted_uid, token, url))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results
    except Exception as e:
        app.logger.error(f"Exception in send_multiple_requests: {e}")
        return None

def create_protobuf(uid):
    try:
        message = uid_generator_pb2.uid_generator()
        message.saturn_ = int(uid)
        message.garena = 1
        return message.SerializeToString()
    except Exception as e:
        app.logger.error(f"Error creating uid protobuf: {e}")
        return None

def enc(uid):
    protobuf_data = create_protobuf(uid)
    if protobuf_data is None:
        return None
    return encrypt_message(protobuf_data)

def make_request(encrypt, server_name, token):
    try:
        if server_name == "IND":
            url = "https://client.ind.freefiremobile.com/GetPlayerPersonalShow"
        elif server_name in {"BR", "US", "SAC", "NA"}:
            url = "https://client.us.freefiremobile.com/GetPlayerPersonalShow"
        else:
            url = "https://clientbp.ggblueshark.com/GetPlayerPersonalShow"
        edata = bytes.fromhex(encrypt)
        headers = {
            'User-Agent': "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
            'Connection': "Keep-Alive",
            'Accept-Encoding': "gzip",
            'Authorization': f"Bearer {token}",
            'Content-Type': "application/x-www-form-urlencoded",
            'Expect': "100-continue",
            'X-Unity-Version': "2018.4.11f1",
            'X-GA': "v1 1",
            'ReleaseVersion': "OB53"
        }
        response = requests.post(url, data=edata, headers=headers, verify=False)
        binary = bytes.fromhex(response.content.hex())
        return decode_protobuf(binary)
    except Exception as e:
        app.logger.error(f"Error in make_request: {e}")
        return None

def decode_protobuf(binary):
    try:
        items = like_count_pb2.Info()
        items.ParseFromString(binary)
        return items
    except DecodeError as e:
        app.logger.error(f"Error decoding Protobuf data: {e}")
        return None
    except Exception as e:
        app.logger.error(f"Unexpected error during protobuf decoding: {e}")
        return None

def fetch_player_info(uid):
    try:
        url = f"https://nr-codex-info.vercel.app/get?uid={uid}"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            account_info = data.get("AccountInfo", {})
            return {
                "Level": account_info.get("AccountLevel", "NA"),
                "Region": account_info.get("AccountRegion", "NA"),
                "ReleaseVersion": account_info.get("ReleaseVersion", "NA")
            }
        return {"Level": "NA", "Region": "NA", "ReleaseVersion": "NA"}
    except Exception as e:
        app.logger.error(f"Error fetching player info: {e}")
        return {"Level": "NA", "Region": "NA", "ReleaseVersion": "NA"}

@app.route('/like', methods=['GET'])
def handle_requests():
    uid = request.args.get("uid")
    server_name = request.args.get("server_name", "").upper()
    if not uid or not server_name:
        return jsonify({"error": "UID and server_name are required"}), 400

    try:
        player_info = fetch_player_info(uid)
        region = player_info["Region"]
        level = player_info["Level"]
        release_version = player_info["ReleaseVersion"]

        if region != "NA" and server_name != region:
            server_name_used = region
        else:
            server_name_used = server_name

        tokens = load_tokens(server_name_used)
        if tokens is None:
            return jsonify({"error": f"No tokens loaded for region {server_name_used}. Please add tokens to the token file."}), 500

        token = tokens[0]['token']
        encrypted_uid = enc(uid)
        if encrypted_uid is None:
            return jsonify({"error": "Encryption of UID failed."}), 500

        before = make_request(encrypted_uid, server_name_used, token)
        if before is None:
            return jsonify({"error": "Failed to retrieve initial player info."}), 500

        data_before = json.loads(MessageToJson(before))
        before_like = int(data_before.get('AccountInfo', {}).get('Likes', 0))

        if server_name_used == "IND":
            like_url = "https://client.ind.freefiremobile.com/LikeProfile"
        elif server_name_used in {"BR", "US", "SAC", "NA"}:
            like_url = "https://client.us.freefiremobile.com/LikeProfile"
        else:
            like_url = "https://clientbp.ggblueshark.com/LikeProfile"

        asyncio.run(send_multiple_requests(uid, server_name_used, like_url))

        after = make_request(encrypted_uid, server_name_used, token)
        if after is None:
            return jsonify({"error": "Failed to retrieve player info after like requests."}), 500

        data_after = json.loads(MessageToJson(after))
        after_like  = int(data_after.get('AccountInfo', {}).get('Likes', 0))
        player_uid  = int(data_after.get('AccountInfo', {}).get('UID', 0))
        player_name = str(data_after.get('AccountInfo', {}).get('PlayerNickname', ''))
        like_given  = after_like - before_like
        status = 1 if like_given != 0 else 2

        return jsonify({
            "LikesGivenByAPI":    like_given,
            "LikesafterCommand":  after_like,
            "LikesbeforeCommand": before_like,
            "PlayerNickname":     player_name,
            "Region":             region,
            "Level":              level,
            "UID":                player_uid,
            "ReleaseVersion":     release_version,
            "status":             status
        })
    except Exception as e:
        app.logger.error(f"Error processing request: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=False, use_reloader=False)
