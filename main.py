import os
import sqlite3
import threading
import time
import traceback
import requests
from flask import Flask
import telebot

# --- ENVIRONMENT VARIABLES ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)

app = Flask(__name__)

# --- DATABASE (SQLite) ---
def init_db():
    conn = sqlite3.connect("downloader.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            downloads_left INTEGER DEFAULT 5,
            is_vip INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

init_db()

def check_user(user_id):
    conn = sqlite3.connect("downloader.db")
    cursor = conn.cursor()
    cursor.execute("SELECT downloads_left, is_vip FROM users WHERE user_id = ?", (user_id,))
    res = cursor.fetchone()
    if not res:
        cursor.execute("INSERT INTO users (user_id, downloads_left) VALUES (?, 5)", (user_id,))
        conn.commit()
        res = (5, 0)
    conn.close()
    return res

def decrease_limit(user_id):
    conn = sqlite3.connect("downloader.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET downloads_left = downloads_left - 1 WHERE user_id = ? AND is_vip = 0", (user_id,))
    conn.commit()
    conn.close()

# --- MEDIA DOWNLOADER LOGIC ---
def download_media(url, user_id):
    if not os.path.exists("downloads"):
        os.makedirs("downloads")

    # Bitta ochiq va barqaror API (Rapid/SnapSave analogi)
    clean_url = url.split("?")[0]
    api_endpoint = f"https://api.vkrnot.ru/instagram?url={clean_url}"
    
    response = requests.get(api_endpoint, timeout=15)
    
    if response.status_code != 200:
        raise Exception(f"API Server Xatosi: Status Code {response.status_code}")
        
    data = response.json()
    video_url = None

    if "url" in data:
        video_url = data["url"]
    elif "data" in data:
        if isinstance(data["data"], dict) and "video_url" in data["data"]:
            video_url = data["data"]["video_url"]
        elif isinstance(data["data"], list) and len(data["data"]) > 0:
            video_url = data["data"][0].get("url") or data["data"][0].get("video_url")

    if not video_url:
        raise Exception(f"Video URL topilmadi. API Javobi: {str(data)[:200]}")

    file_path = f"downloads/{user_id}_{int(time.time())}.mp4"
    video_bytes = requests.get(video_url, stream=True, timeout=30)
    
    with open(file_path, "wb") as f:
        for chunk in video_bytes.iter_content(chunk_size=1024*1024):
            if chunk:
                f.write(chunk)

    return file_path

# --- FLASK WEB SERVER ---
@app.route("/")
def home():
    return "Media Downloader Bot Is Live!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# --- TELEGRAM BOT HANDLERS ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.clear_step_handler_by_chat_id(chat_id=message.chat.id)
    user_id = message.from_user.id
    limit, is_vip = check_user(user_id)
    
    status = "🌟 VIP Foydalanuvchi (Limitsiz)" if is_vip else f"🆓 Bepul limit: {limit} ta video"
    
    bot.send_message(
        message.chat.id,
        f"Assalomu alaykum! Men Instagram va TikTok'dan video yuklab beruvchi botman.\n\n"
        f"Sizning statusingiz: {status}\n\n"
        f"Menga Instagram Reels yoki TikTok havolasini yuboring!"
    )

@bot.message_handler(func=lambda msg: True)
def handle_link(message):
    url = message.text.strip()
    user_id = message.from_user.id
    limit, is_vip = check_user(user_id)

    if not ("instagram.com" in url or "tiktok.com" in url or "youtu.be" in url or "youtube.com" in url):
        bot.reply_to(message, "⚠️ Iltimos, faqat Instagram, TikTok yoki YouTube havolasini yuboring.")
        return

    if not is_vip and limit <= 0:
        bot.reply_to(
            message, 
            "❌ <b>Kunlik bepul limiteringiz tugadi!</b>\n\n"
            "Limitsiz yuklash uchun <b>VIP obuna</b> xarid qiling yoki do'stlaringizga ulashing.",
            parse_mode="HTML"
        )
        return

    status_msg = bot.reply_to(message, "⏳ Video yuklanmoqda, kuting...")

    try:
        file_path = download_media(url, user_id)

        with open(file_path, 'rb') as video:
            bot.send_video(message.chat.id, video, caption="✅ Video yuklab olindi!")

        decrease_limit(user_id)
        bot.delete_message(message.chat.id, status_msg.message_id)

        if os.path.exists(file_path):
            os.remove(file_path)

    except Exception as e:
        error_details = traceback.format_exc()
        print(f"Xatolik: {error_details}")
        # Aniq xatolikni chatga chiqarish (Debugging uchun)
        bot.edit_message_text(f"❌ Xatolik yuz berdi:\n<code>{str(e)[:300]}</code>", message.chat.id, status_msg.message_id, parse_mode="HTML")

# --- MAIN RUNNER ---
if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    print("Media Downloader Bot ishga tushdi...")
    
    while True:
        try:
            bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except Exception as e:
            print(f"Polling xatosi: {e}")
            time.sleep(3)
