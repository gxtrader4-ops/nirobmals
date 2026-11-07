import asyncio
import logging
import sqlite3
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from pytgcalls import PyTgCalls

# ------------------ CONFIGURATION ------------------
API_ID = 33513698  
API_HASH = "42f0233fe525aed5338c1251622f2e23"  

BOT_TOKEN = "9175270490:AAFuoLJ6XuD_iLMaSfkbYYLYWWmTqL3h-fE"
ADMIN_ID = 8419760844

# ------------------ DATABASE SETUP ------------------
conn = sqlite3.connect("bot_data.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS user_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_string TEXT
)
""")
conn.commit()

# Default Settings Data Setup
default_texts = {
    "start_text": "👋 **স্বাগতম!**\n\nআপনি কোন গ্রুপের মধ্যে আমাদের এই বটটি সেটআপ করতে চাচ্ছেন? আপনার **Public Group Link** পাঠাই দিন।",
    "btn_emoji": "🎙️",
    "connect_msg": "✅ আপনার গ্রুপ লিংক রিসিভ হয়েছে! গ্রুপে বট/অ্যাকাউন্টকে অ্যাডমিন পাওয়ার দিন। ভয়েস লাইভ চালু হলেই অটোমেটিক জয়েন করে সবাইকে Unmute করে দেওয়া হবে।"
}

for k, v in default_texts.items():
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
conn.commit()

def get_db(key):
    cursor.execute("SELECT value FROM settings WHERE key=?", (key,))
    res = cursor.fetchone()
    return res[0] if res else ""

def set_db(key, val):
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, val))
    conn.commit()

# ------------------ CLIENT SETUP ------------------
bot = Client("unmute_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# User state handling for admin dynamic emoji/text setup
user_states = {}

# ------------------ BOT HANDLERS ------------------

@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client, message: Message):
    if message.from_user.id == ADMIN_ID:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{get_db('btn_emoji')} অ্যাডমিন প্যানেল", callback_data="admin_panel")],
            [InlineKeyboardButton("➕ ইউজার অ্যাকাউন্ট (Session) যোগ করুন", callback_data="add_session")],
            [InlineKeyboardButton("✨ প্রিমিয়াম / টেক্সট & ইমোজি সেটআপ", callback_data="custom_settings")]
        ])
        await message.reply_text("👑 **হ্যালো মালিক!** এটি আপনার অ্যাডমিন কন্ট্রোল প্যানেল।", reply_markup=kb)
    else:
        text = get_db("start_text")
        await message.reply_text(text)

@bot.on_message(filters.private & ~filters.me)
async def handle_private_messages(client, message: Message):
    uid = message.from_user.id
    text = message.text

    # Admin customization states
    if uid == ADMIN_ID and uid in user_states:
        state = user_states[uid]
        if state == "WAIT_START_TEXT":
            set_db("start_text", text)
            del user_states[uid]
            await message.reply_text("✅ স্টার্ট টেক্সট সফলভাবে আপডেট করা হয়েছে!")
            return
        elif state == "WAIT_EMOJI":
            set_db("btn_emoji", text)
            del user_states[uid]
            await message.reply_text(f"✅ বোতাম ইমোজি `{text}` আপডেট করা হয়েছে!")
            return
        elif state == "WAIT_SESSION":
            cursor.execute("INSERT INTO user_sessions (session_string) VALUES (?)", (text,))
            conn.commit()
            del user_states[uid]
            await message.reply_text("✅ নতুন Telegram User Session সফলভাবে যুক্ত হয়েছে!")
            return

    # Group link processing for users
    if "t.me/" in text or "@" in text:
        connect_msg = get_db("connect_msg")
        await message.reply_text(f"{connect_msg}\n\nTarget: `{text}`")

@bot.on_callback_query()
async def callback_handler(client, query):
    data = query.data
    uid = query.from_user.id

    if uid != ADMIN_ID:
        await query.answer("❌ আপনি এই অপশনের অনুমতিপ্রাপ্ত নন!", show_alert=True)
        return

    if data == "admin_panel":
        await query.message.edit_text("⚙️ **অ্যাডমিন কন্ট্রোল সেন্টার**")
    
    elif data == "custom_settings":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 Change Start Text", callback_data="set_start_txt")],
            [InlineKeyboardButton("🎨 Change Button Emoji", callback_data="set_emoji")]
        ])
        await query.message.edit_text("⚙️ **কাস্টমাইজেশন ও প্রিমিয়াম সেটিংস**\nএখানে আপনি আপনার পছন্দমতো টেলিগ্রাম টেক্সট ও ইমোজি সেট করতে পারবেন:", reply_markup=kb)

    elif data == "set_start_txt":
        user_states[uid] = "WAIT_START_TEXT"
        await query.message.reply_text("নতুন **Start Text** পাঠাও:")

    elif data == "set_emoji":
        user_states[uid] = "WAIT_EMOJI"
        await query.message.reply_text("যেকোনো **Telegram Emoji** লিখে পাঠাও:")

    elif data == "add_session":
        user_states[uid] = "WAIT_SESSION"
        await query.message.reply_text("আপনার Pyrogram/Telethon **String Session** কোডটি পাঠাও:")

# ------------------ AUTOMATIC VOICE CHAT UNMUTER ------------------

async def run_user_account_unmuter():
    """
    এই ফাংশনটি ডাটাবেজে থাকা ইউজার অ্যাকাউন্টগুলো ব্যাকগ্রাউন্ডে চালিয়ে রাখবে। 
    লাইভ ভয়েস চ্যাট চালু হলে সাথে সাথে মাইক আনমিউট করবে।
    """
    cursor.execute("SELECT session_string FROM user_sessions")
    sessions = cursor.fetchall()
    
    for sess in sessions:
        try:
            user_app = Client("user_sess", api_id=API_ID, api_hash=API_HASH, session_string=sess[0])
            pytgcalls = PyTgCalls(user_app)
            
            @pytgcalls.on_participant_speaking()
            async def unmute_everyone(app, chat_id, participant):
                # ভয়েস চ্যাটে কেউ স্পিক বা জয়েন করলে তাকে অটোমেটিক Unmute করবে
                try:
                    await user_app.unmute_chat_member(chat_id, participant.user_id)
                except Exception:
                    pass

            await user_app.start()
            await pytgcalls.start()
        except Exception as e:
            logging.error(f"Session error: {e}")
# ------------------ RUN BOT ------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("🤖 Bot is starting...")
    
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    loop.create_task(run_user_account_unmuter())
    bot.run()
