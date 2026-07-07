import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import threading
import oliev
import guidely
import kdcampus
import kgs
import utkarsh
import allen
import adda247  # Naya module import

bot = telebot.TeleBot('8840274547:AAGqA7dYBSlAWPA9QF0N2zW1uvoUeTu9lY0')
user_prompts = {}

@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🤖 Olievboard", callback_data='oliev'),
        InlineKeyboardButton("📚 Guidely", callback_data='guidely'),
        InlineKeyboardButton("🎓 KD Campus", callback_data='kdcampus'),
        InlineKeyboardButton("📖 Khan GS", callback_data='kgs'),
        InlineKeyboardButton("🎯 Utkarsh", callback_data='utkarsh'),
        InlineKeyboardButton("🎓 Allen", callback_data='allen'),
        InlineKeyboardButton("📱 Adda247", callback_data='adda247')  # Naya Button
    )
    bot.send_message(message.chat.id, "✨ Choose Target Platform:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback_router(call):
    handlers = {
        'oliev': ("Olievboard", oliev),
        'guidely': ("Guidely", guidely),
        'kdcampus': ("KD Campus", kdcampus),
        'kgs': ("Khan GS", kgs),
        'utkarsh': ("Utkarsh", utkarsh),
        'allen': ("Allen", allen),
        'adda247': ("Adda247", adda247)
    }
    
    if call.data in handlers:
        platform_name, module = handlers[call.data]
        msg = bot.send_message(call.message.chat.id, f"📂 Please upload your combo.txt file for {platform_name}:")
        user_prompts[call.message.chat.id] = msg.message_id
        bot.register_next_step_handler(msg, lambda m: process_combo_file(m, platform_name, module))

def process_combo_file(message, platform_name, module):
    if message.document:
        try:
            bot.delete_message(message.chat.id, user_prompts.get(message.chat.id, 0))
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass

        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        filename = f"combo_{message.chat.id}.txt"
        with open(filename, "wb") as new_file:
            new_file.write(downloaded_file)
        
        progress_text = f"""╭───☀ 𝖢𝖧𝖤𝖢𝖪𝖨𝖭𝖦 ☀───╮
┣ ⚙️ ■■▢▢▢▢▢▢ 
┣ 📊 Hit : 0
┣ 📂 Loaded : 0/0
┣ 🔥 Status : Starting {platform_name}...
╰─── 𝐂𝐡𝐞𝐜𝐤𝐞𝐫 𝐁𝐨𝐭 ───╯"""
        
        progress_msg = bot.send_message(message.chat.id, progress_text)
        
        thread = threading.Thread(target=module.run_check, args=(bot, message.chat.id, progress_msg.message_id, filename, platform_name))
        thread.start()
    else:
        bot.send_message(message.chat.id, "❌ Please send a valid text file.")

if __name__ == '__main__':
    print("🤖 Bot started...")
    bot.infinity_polling()